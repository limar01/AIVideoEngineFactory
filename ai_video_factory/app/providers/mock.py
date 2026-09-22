"""MockVideoProvider — deterministic fake provider for automated testing.

Source: docs/PROVIDER_INTERFACE.md §3.1, Master Spec §27 (test with mock, never real quota)
        docs/SNAPGEN_RECON.md (real provider recon)

This provider implements the full VideoGenerationProvider interface but:
- Authentication: always succeeds
- Quota: configurable (default 10,000/day — never exhausts in tests)
- Generation: creates a real tiny MP4 using ffmpeg testsrc (not a fake file)
- Errors: can be configured to fail on the Nth call for failure-injection tests

The MockVideoProvider is the ONLY provider used in automated tests.
"""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from uuid import uuid4

from app.providers.base import (
    GenerationCapabilities,
    GenerationResult,
    GenerationStatus,
    QuotaInfo,
    VideoGenerationProvider,
)

logger = logging.getLogger(__name__)


class MockVideoProvider(VideoGenerationProvider):
    """Deterministic mock provider that uses ffmpeg test-pattern videos.

    All generation is reproducible with no network and no provider quota.
    """

    PROVIDER_NAME = "mock"

    def __init__(
        self,
        quota_limit: int = 10000,
        fail_on_call: int | None = None,
        fail_with_error: str = "SIMULATED_ERROR",
        output_dir: str | Path | None = None,
        min_duration: float = 2.0,
        max_duration: float = 5.0,
    ) -> None:
        self._quota_limit = quota_limit
        self._used = 0
        self._fail_on_call = fail_on_call
        self._fail_with_error = fail_with_error
        self._call_count = 0
        self._output_dir = Path(output_dir) if output_dir else Path(tempfile.gettempdir())
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._min_duration = min_duration
        self._max_duration = max_duration

        # Track generated results: result_id -> filepath
        self._results: dict[str, str] = {}

        # Session state
        self._authenticated = False

    # ------------------------------------------------------------------ #
    # Authentication
    # ------------------------------------------------------------------ #

    def authenticate(self, account_credentials: dict) -> bool:
        """Always succeeds for mock — no real auth needed."""
        self._authenticated = True
        self._reset_quota()
        logger.info("MockVideoProvider authenticated (mock — always succeeds)")
        return True

    def check_session(self) -> bool:
        return self._authenticated

    def _reset_quota(self) -> None:
        self._used = 0
        reset_time = datetime.utcnow() + timedelta(days=1)
        self._quota = QuotaInfo(
            limit=self._quota_limit,
            used=self._used,
            remaining=self._quota_limit - self._used,
            reset_time=reset_time.isoformat(),
        )

    # ------------------------------------------------------------------ #
    # Capabilities
    # ------------------------------------------------------------------ #

    def get_capabilities(self) -> GenerationCapabilities:
        return GenerationCapabilities(
            max_prompt_length=2000,
            supported_aspect_ratios=["16:9", "9:16", "4:3"],
            supported_resolutions=["1080x1920", "720x1280", "720x480"],
            max_duration_seconds=self._max_duration,
            min_duration_seconds=self._min_duration,
            supports_narration=False,
        )

    # ------------------------------------------------------------------ #
    # Quota
    # ------------------------------------------------------------------ #

    def get_quota(self) -> QuotaInfo:
        return QuotaInfo(
            limit=self._quota_limit,
            used=self._used,
            remaining=max(0, self._quota_limit - self._used),
            reset_time=(datetime.utcnow() + timedelta(days=1)).isoformat(),
        )

    # ------------------------------------------------------------------ #
    # Generation
    # ------------------------------------------------------------------ #

    def submit_generation(self, prompt: str, scene_metadata: dict) -> GenerationResult:
        self._call_count += 1

        # Failure injection for testing
        if self._fail_on_call is not None and self._call_count == self._fail_on_call:
            logger.warning("MockVideoProvider injecting failure on call #%d", self._call_count)
            return GenerationResult(
                success=False,
                result_id=None,
                error_code=self._fail_with_error,
                error_message="Simulated generation error",
                download_url=None,
                estimated_wait_seconds=0,
            )

        # Generate a real test-pattern video using ffmpeg
        result_id = str(uuid4())
        output_path = self._output_dir / f"mock_{result_id}.mp4"

        duration = scene_metadata.get("target_clip_seconds", 8.0)
        # Clamp to mock-supported range
        duration = max(self._min_duration, min(self._max_duration, duration))

        # Use ffmpeg to generate a test pattern video
        # testsrc = test pattern, sine wave audio at 440Hz
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"testsrc=duration={duration}:size=720x1280:rate=24",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=3.0",
            "-c:v", "libx264", "-c:a", "aac",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            return GenerationResult(
                success=False,
                result_id=None,
                error_code="FFMPEG_ERROR",
                error_message=e.stderr.decode() if e.stderr else str(e),
                download_url=None,
                estimated_wait_seconds=0,
            )

        self._results[result_id] = str(output_path)
        self._used += 1

        return GenerationResult(
            success=True,
            result_id=result_id,
            error_code=None,
            error_message=None,
            download_url=f"file://{output_path}",
            estimated_wait_seconds=0,  # mock is instant
        )

    def get_generation_status(self, result_id: str) -> GenerationStatus:
        if result_id not in self._results:
            return GenerationStatus.FAILED
        # Mock is always "completed" after submit (instant)
        path = Path(self._results[result_id])
        if path.exists():
            return GenerationStatus.COMPLETED
        return GenerationStatus.FAILED

    def download_result(self, result_id: str) -> bytes:
        path = self._results.get(result_id)
        if not path or not Path(path).exists():
            raise FileNotFoundError(f"Mock result not found: {result_id}")
        return Path(path).read_bytes()

    def download_result_to_file(self, result_id: str, dest: str | Path) -> Path:
        """Like download_result, but writes to a file (avoids loading large bytes)."""
        path = self._results.get(result_id)
        if not path or not Path(path).exists():
            raise FileNotFoundError(f"Mock result not found: {result_id}")
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Copy file
        import shutil
        shutil.copy2(path, dest)
        return dest

    # ------------------------------------------------------------------ #
    # Error / quota detection
    # ------------------------------------------------------------------ #

    def detect_error(self, result_id: str, raw_response: str) -> tuple[Optional[str], Optional[str]]:
        # Mock: never has errors unless failure injection is configured
        return (None, None)

    def detect_quota_exhaustion(self, raw_response: str) -> bool:
        return self._quota_limit <= self._used

    # ------------------------------------------------------------------ #
    # Cleanup
    # ------------------------------------------------------------------ #

    def close_session(self) -> None:
        # Clean up generated mock files
        for path in self._results.values():
            try:
                os.unlink(path)
            except OSError:
                pass
        self._results.clear()
        self._authenticated = False
        logger.info("MockVideoProvider session closed")
