"""Video Quality Assurance (VideoQA) — validates downloaded clips before assembly.

Source: docs/ARCHITECTURE.md §4.12 (qa/), Master Spec §17 (QA pipeline)

Checks each clip for:
- File existence and non-zero size
- Valid MP4 container (via ffprobe)
- Video codec (H.264 expected)
- Audio codec (AAC expected)
- Resolution (within expected range)
- Duration (within expected range)
- Frame rate (within expected range)

Results are stored per-clip and aggregated for the assembly gate check.

The mock provider generates ffmpeg testsrc videos that always pass these checks.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class QAFinding:
    """A single QA check result for one clip."""

    check_name: str
    passed: bool
    message: str = ""
    detail: str = ""

    @property
    def is_failure(self) -> bool:
        return not self.passed


@dataclass
class QAResult:
    """Full QA report for one clip."""

    clip_path: Path
    clip_id: str
    findings: list[QAFinding] = field(default_factory=list)
    overall_pass: bool = False
    checked_at: str = ""

    @property
    def failures(self) -> list[QAFinding]:
        return [f for f in self.findings if f.is_failure]

    @property
    def failure_count(self) -> int:
        return len(self.failures)

    def add_finding(self, finding: QAFinding) -> None:
        self.findings.append(finding)
        # Update overall pass: pass only if ALL findings pass
        self.overall_pass = all(f.passed for f in self.findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "clip_path": str(self.clip_path),
            "clip_id": self.clip_id,
            "overall_pass": self.overall_pass,
            "failure_count": self.failure_count,
            "findings": [
                {
                    "check_name": f.check_name,
                    "passed": f.passed,
                    "message": f.message,
                    "detail": f.detail,
                }
                for f in self.findings
            ],
        }


# ---------------------------------------------------------------------------
# VideoQA
# ---------------------------------------------------------------------------


class VideoQA:
    """Runs quality assurance checks on downloaded video clips.

    All checks use ``ffprobe`` (from ffmpeg) to inspect the clip file.
    No provider calls are made — this operates purely on local files.

    Results can be used by the assembly step to decide whether to include
    a clip in the final video.
    """

    def __init__(
        self,
        expected_min_duration: float = 1.0,
        expected_max_duration: float = 30.0,
        expected_min_resolution: tuple[int, int] = (180, 320),
        expected_max_resolution: tuple[int, int] = (4096, 4096),
        expected_codec_video: str = "h264",
        expected_codec_audio: str = "aac",
        expected_min_fps: float = 10.0,
        expected_max_fps: float = 60.0,
    ) -> None:
        self.expected_min_duration = expected_min_duration
        self.expected_max_duration = expected_max_duration
        self.expected_min_resolution = expected_min_resolution
        self.expected_max_resolution = expected_max_resolution
        self.expected_codec_video = expected_codec_video
        self.expected_codec_audio = expected_codec_audio
        self.expected_min_fps = expected_min_fps
        self.expected_max_fps = expected_max_fps

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_clip(self, clip_path: Path, clip_id: str = "") -> QAResult:
        """Run all QA checks on a single clip file."""
        clip_id = clip_id or clip_path.stem
        result = QAResult(
            clip_path=clip_path,
            clip_id=clip_id,
            checked_at=self._now_iso(),
        )

        if not clip_path.exists():
            result.add_finding(QAFinding(
                check_name="file_exists",
                passed=False,
                message="Clip file does not exist",
                detail=str(clip_path),
            ))
            return result

        size = clip_path.stat().st_size
        if size == 0:
            result.add_finding(QAFinding(
                check_name="file_size",
                passed=False,
                message="Clip file is empty (0 bytes)",
                detail=str(clip_path),
            ))
            return result

        result.add_finding(QAFinding(
            check_name="file_size",
            passed=True,
            message=f"File size OK ({size} bytes)",
            detail=f"{size} bytes",
        ))

        # Probe the file
        probe = self._probe(clip_path)
        if probe is None:
            result.add_finding(QAFinding(
                check_name="valid_container",
                passed=False,
                message="Could not probe file (not a valid video or ffprobe error)",
                detail=str(clip_path),
            ))
            return result

        result.add_finding(QAFinding(
            check_name="valid_container",
            passed=True,
            message="Valid video container",
            detail=f"{probe.get('format_name', 'unknown')}",
        ))

        # Codec checks
        self._check_video_codec(result, probe)
        self._check_audio_codec(result, probe)

        # Resolution check
        self._check_resolution(result, probe)

        # Duration check
        self._check_duration(result, probe)

        # Frame rate check
        self._check_fps(result, probe)

        logger.info(
            "VideoQA.check_clip — %s: %d/%d checks passed",
            clip_id,
            len([f for f in result.findings if f.passed]),
            len(result.findings),
        )

        return result

    def check_clips(self, clip_paths: list[Path]) -> list[QAResult]:
        """Run QA on multiple clips."""
        return [self.check_clip(p) for p in clip_paths]

    # ------------------------------------------------------------------
    # Internal: probing
    # ------------------------------------------------------------------

    def _probe(self, clip_path: Path) -> dict[str, Any] | None:
        """Run ffprobe and return parsed JSON output, or None on failure."""
        try:
            proc = subprocess.run(
                [
                    "ffprobe",
                    "-v", "quiet",
                    "-print_format", "json",
                    "-show_format",
                    "-show_streams",
                    str(clip_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode != 0:
                logger.warning("ffprobe failed for %s: %s", clip_path, proc.stderr)
                return None

            import json
            data = json.loads(proc.stdout)
            return data
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError) as exc:
            logger.warning("ffprobe error for %s: %s", clip_path, exc)
            return None

    # ------------------------------------------------------------------
    # Internal: individual checks
    # ------------------------------------------------------------------

    def _find_stream(self, probe: dict[str, Any], stream_type: str) -> dict[str, Any] | None:
        """Find the first stream of the given type."""
        for stream in probe.get("streams", []):
            if stream.get("codec_type") == stream_type:
                return stream
        return None

    def _check_video_codec(self, result: QAResult, probe: dict[str, Any]) -> None:
        video_stream = self._find_stream(probe, "video")
        if video_stream is None:
            result.add_finding(QAFinding(
                check_name="video_codec",
                passed=False,
                message="No video stream found",
            ))
            return

        codec = video_stream.get("codec_name", "").lower()
        result.add_finding(QAFinding(
            check_name="video_codec",
            passed=(codec == self.expected_codec_video),
            message=(
                "Video codec OK"
                if codec == self.expected_codec_video
                else f"Unexpected video codec: {codec}"
            ),
            detail=f"codec={codec}, expected={self.expected_codec_video}",
        ))

    def _check_audio_codec(self, result: QAResult, probe: dict[str, Any]) -> None:
        audio_stream = self._find_stream(probe, "audio")
        if audio_stream is None:
            # Some clips may not have audio — not a hard failure
            result.add_finding(QAFinding(
                check_name="audio_codec",
                passed=True,
                message="No audio stream (acceptable)",
                detail="audio stream absent",
            ))
            return

        codec = audio_stream.get("codec_name", "").lower()
        result.add_finding(QAFinding(
            check_name="audio_codec",
            passed=(codec == self.expected_codec_audio),
            message=(
                "Audio codec OK"
                if codec == self.expected_codec_audio
                else f"Unexpected audio codec: {codec}"
            ),
            detail=f"codec={codec}, expected={self.expected_codec_audio}",
        ))

    def _check_resolution(self, result: QAResult, probe: dict[str, Any]) -> None:
        video_stream = self._find_stream(probe, "video")
        if video_stream is None:
            return

        width = int(video_stream.get("width", 0))
        height = int(video_stream.get("height", 0))

        min_w, min_h = self.expected_min_resolution
        max_w, max_h = self.expected_max_resolution

        passed = (
            width >= min_w
            and height >= min_h
            and width <= max_w
            and height <= max_h
        )

        result.add_finding(QAFinding(
            check_name="resolution",
            passed=passed,
            message=(
                f"Resolution OK ({width}x{height})"
                if passed
                else f"Resolution out of range: {width}x{height}"
            ),
            detail=(
                f"{width}x{height} (expected {min_w}x{min_h} to {max_w}x{max_h})"
            ),
        ))

    def _check_duration(self, result: QAResult, probe: dict[str, Any]) -> None:
        fmt = probe.get("format", {})
        duration_str = fmt.get("duration", "0")
        try:
            duration = float(duration_str)
        except ValueError:
            result.add_finding(QAFinding(
                check_name="duration",
                passed=False,
                message="Could not parse duration",
                detail=f"raw={duration_str}",
            ))
            return

        passed = self.expected_min_duration <= duration <= self.expected_max_duration
        result.add_finding(QAFinding(
            check_name="duration",
            passed=passed,
            message=(
                f"Duration OK ({duration:.2f}s)"
                if passed
                else f"Duration out of range: {duration:.2f}s"
            ),
            detail=(
                f"{duration:.2f}s (expected {self.expected_min_duration}s to "
                f"{self.expected_max_duration}s)"
            ),
        ))

    def _check_fps(self, result: QAResult, probe: dict[str, Any]) -> None:
        video_stream = self._find_stream(probe, "video")
        if video_stream is None:
            return

        # FPS might be in r_frame_rate (e.g. "24/1") or avg_frame_rate
        fps_str = video_stream.get("r_frame_rate", "0/1")
        try:
            num, denom = fps_str.split("/")
            fps = float(num) / float(denom) if float(denom) != 0 else 0.0
        except (ValueError, ZeroDivisionError):
            fps = 0.0

        passed = self.expected_min_fps <= fps <= self.expected_max_fps
        result.add_finding(QAFinding(
            check_name="frame_rate",
            passed=passed,
            message=(
                f"Frame rate OK ({fps:.1f} fps)"
                if passed
                else f"Frame rate out of range: {fps:.1f} fps"
            ),
            detail=(
                f"{fps:.1f} fps (expected {self.expected_min_fps} to "
                f"{self.expected_max_fps} fps)"
            ),
        ))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _now_iso() -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Assembly gate check
# ---------------------------------------------------------------------------


class AssemblyGate:
    """Decides whether a set of QA'd clips is ready for assembly.

    Uses configurable thresholds from docs/CONFIG_SPEC.md §7:
    - min_pass_rate: minimum fraction of clips that must pass QA
    - max_failures: hard cap on total failures (stops assembly if exceeded)
    """

    def __init__(
        self,
        min_pass_rate: float = 0.85,
        max_failures: int = 3,
    ) -> None:
        self.min_pass_rate = min_pass_rate
        self.max_failures = max_failures

    def evaluate(self, results: list[QAResult]) -> tuple[bool, list[str]]:
        """Evaluate whether the clip set passes the gate.

        Returns:
            (allowed, reasons) where allowed is True if assembly may proceed.
        """
        if not results:
            return False, ["No clips to evaluate"]

        total = len(results)
        passed = sum(1 for r in results if r.overall_pass)
        failed = total - passed
        pass_rate = passed / total if total > 0 else 0.0

        reasons: list[str] = []

        if failed > self.max_failures:
            reasons.append(
                f"Too many QA failures: {failed} > max {self.max_failures}"
            )

        if pass_rate < self.min_pass_rate:
            reasons.append(
                f"Pass rate too low: {pass_rate:.1%} < {self.min_pass_rate:.1%}"
            )

        allowed = len(reasons) == 0
        if not allowed:
            logger.warning("AssemblyGate.evaluate — BLOCKED: %s", "; ".join(reasons))

        return allowed, reasons
