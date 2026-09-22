"""Video assembly — combines clips + narration into the final video.

Source: docs/ARCHITECTURE.md §4.10 (assembly/), Master Spec §15 (assembly step)

Uses FFmpeg to:
1. Concatenate video clips (with optional crossfade transitions)
2. Add narration audio (from TTS output or generated voiceover)
3. Burn in subtitles if provided
4. Output final MP4 at the target resolution/duration

The assembler is stateless — it takes a list of clip paths + narration and
produces a final video file. No database interaction.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class AssemblyConfig:
    """Configuration for the assembly step."""

    output_dir: str | Path = "output"
    target_resolution: tuple[int, int] = (1280, 720)  # 720p landscape
    target_fps: int = 24
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    audio_bitrate: str = "128k"
    crossfade_duration: float = 0.5  # seconds between clips (0 = hard cut)
    subtitle_font_size: int = 24
    subtitle_font: str = "sans-serif"
    max_total_duration: float = 600.0  # 10 minutes max


# ---------------------------------------------------------------------------
# Assembly input
# ---------------------------------------------------------------------------


@dataclass
class AssemblyInput:
    """What the assembler needs to produce the final video."""

    clips: list[Path] = field(default_factory=list)
    """Ordered list of clip paths to concatenate."""

    narration_audio: Path | None = None
    """Optional narration/TTS audio file (MP3/WAV) to mix in."""

    narration_tracks: list[Path] = field(default_factory=list)
    """Per-clip narration audio tracks (one per clip, optional)."""

    subtitles: str | None = None
    """Optional SRT subtitle content (as a string)."""

    config: AssemblyConfig = field(default_factory=AssemblyConfig)


# ---------------------------------------------------------------------------
# AssemblyResult
# ---------------------------------------------------------------------------


@dataclass
class AssemblyResult:
    """Result of an assembly operation."""

    success: bool
    output_path: Path | None = None
    error_message: str = ""
    duration_seconds: float = 0.0
    file_size_bytes: int = 0
    ffmpeg_log: str = ""


# ---------------------------------------------------------------------------
# VideoAssembler
# ---------------------------------------------------------------------------


class VideoAssembler:
    """Stateless FFmpeg-based video assembler.

    Takes ``AssemblyInput`` and produces a final MP4.
    No database or provider interaction — pure FFmpeg wrapper.
    """

    def __init__(self, config: AssemblyConfig | None = None) -> None:
        self.config = config or AssemblyConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assemble(self, input: AssemblyInput) -> AssemblyResult:
        """Assemble the final video from the given input."""
        result = AssemblyResult(success=False)

        if not input.clips:
            result.error_message = "No clips provided for assembly"
            return result

        self.config.output_dir = Path(self.config.output_dir)
        self.config.output_dir.mkdir(parents=True, exist_ok=True)

        # Determine output filename
        timestamp = self._timestamp()
        output_path = self.config.output_dir / f"final_{timestamp}.mp4"

        try:
            ffmpeg_cmd = self._build_command(input, output_path)

            logger.info(
                "VideoAssembler.assemble — running FFmpeg (%d args)",
                len(ffmpeg_cmd),
            )

            proc = subprocess.run(
                ffmpeg_cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minutes max for assembly
            )

            if proc.returncode != 0:
                result.error_message = f"FFmpeg failed (exit {proc.returncode}): {proc.stderr[:500]}"
                result.ffmpeg_log = proc.stderr
                logger.error("VideoAssembler.assemble — FFmpeg error: %s", result.error_message)
                return result

            # Verify output
            if not output_path.exists():
                result.error_message = f"Output file not created: {output_path}"
                return result

            size = output_path.stat().st_size
            duration = self._probe_duration(output_path)

            result.success = True
            result.output_path = output_path
            result.file_size_bytes = size
            result.duration_seconds = duration
            result.ffmpeg_log = proc.stderr

            logger.info(
                "VideoAssembler.assemble — SUCCESS: %s (%d bytes, %.1f seconds)",
                output_path,
                size,
                duration,
            )

            return result

        except subprocess.TimeoutExpired:
            result.error_message = "FFmpeg timed out after 600 seconds"
            return result
        except Exception as exc:
            result.error_message = str(exc)
            return result

    # ------------------------------------------------------------------
    # Command builder
    # ------------------------------------------------------------------

    def _build_command(
        self, input: AssemblyInput, output: Path
    ) -> list[str]:
        """Build the FFmpeg command for the given input."""
        cfg = self.config
        args: list[str] = [
            "ffmpeg",
            "-y",  # overwrite output
            "-hide_banner",
            "-loglevel", "warning",
        ]

        # --- Input: clips ---
        for i, clip_path in enumerate(input.clips):
            args.extend(["-i", str(clip_path)])

        # --- Input: narration (global) ---
        if input.narration_audio and input.narration_audio.exists():
            args.extend(["-i", str(input.narration_audio)])

        # --- Input: per-clip narration ---
        for track_path in input.narration_tracks:
            if track_path.exists():
                args.extend(["-i", str(track_path)])

        # --- Audio availability (2026-09-22 fix: silent-clip graphs) ---
        narration_present = bool(
            (input.narration_audio and input.narration_audio.exists())
            or any(t.exists() for t in input.narration_tracks)
        )
        clips_have_audio = bool(input.clips) and all(
            self._has_audio(p) for p in input.clips
        )

        # --- Filter complex ---
        filter_complex = self._build_filter_graph(
            input,
            len(input.clips),
            clips_have_audio=clips_have_audio,
            narration_present=narration_present,
        )

        if filter_complex:
            args.extend(["-filter_complex", filter_complex])

        # --- Map outputs ---
        # Main video output
        args.extend(["-map", "[vout]"])

        # Audio output (only when the graph actually produces one)
        if clips_have_audio or narration_present:
            args.extend(["-map", "[aout]"])

        # --- Encoding options ---
        args.extend([
            "-c:v", cfg.video_codec,
            "-preset", "fast",
            "-crf", "23",
            "-c:a", cfg.audio_codec,
            "-b:a", cfg.audio_bitrate,
            "-r", str(cfg.target_fps),
            "-pix_fmt", "yuv420p",
            "-shortest",  # trim to shortest stream
        ])

        # --- Subtitles ---
        if input.subtitles:
            # Write subtitles to a temp file
            srt_path = Path(tempfile.mktemp(suffix=".srt"))
            srt_path.write_text(input.subtitles)
            try:
                args.extend([
                    "-vf", f"subtitles={srt_path}:force_style='FontSize={cfg.subtitle_font_size}'"
                ])
            finally:
                srt_path.unlink(missing_ok=True)

        # --- Output ---
        args.append(str(output))

        return args

    def _build_filter_graph(
        self,
        input: AssemblyInput,
        num_clip_inputs: int,
        *,
        clips_have_audio: bool = True,
        narration_present: bool = False,
    ) -> str:
        """Build the FFmpeg filter_complex graph string.

        Handles:
        - Concatenation of video clips (with optional crossfade)
        - Mixing narration audio
        - Scaling to target resolution
        - Silent (video-only) clips: no audio chain, no [aout]
          (2026-09-22 fix — previously the graph always referenced [i:a]
          and emitted an unconnected [aout], exit 234 on silent clips)
        """
        w, h = self.config.target_resolution

        # --- video chain ---
        if num_clip_inputs == 1:
            video_chain = f"[0:v]scale={w}:{h}[vout];"
        else:
            v_inputs = [
                f"[{i}:v]scale={w}:{h}[v{i}];" for i in range(num_clip_inputs)
            ]
            if self.config.crossfade_duration > 0:
                video_chain = self._build_xfade_chain(v_inputs, num_clip_inputs)
            else:
                concat_v = "".join(f"[v{i}]" for i in range(num_clip_inputs))
                video_chain = (
                    f"{concat_v}concat=n={num_clip_inputs}:v=1[vout];"
                )

        # --- audio chain (only when a source actually has audio) ---
        if clips_have_audio:
            if num_clip_inputs == 1:
                audio_chain = (
                    "[0:a]aformat=sample_fmts=fltp:channel_layouts=stereo[aout]"
                )
            else:
                a_inputs = [
                    f"[{i}:a]aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}];"
                    for i in range(num_clip_inputs)
                ]
                if self.config.crossfade_duration > 0:
                    audio_chain = self._build_acrossfade_chain(
                        a_inputs, num_clip_inputs
                    )
                else:
                    concat_a = "".join(f"[a{i}]" for i in range(num_clip_inputs))
                    audio_chain = (
                        f"{concat_a}concat=n={num_clip_inputs}:a=1[aout];"
                    )
            return video_chain + audio_chain

        if narration_present:
            # Silent clips + narration: wire the first present narration input.
            idx = num_clip_inputs
            narr_idx = None
            if input.narration_audio and input.narration_audio.exists():
                narr_idx = idx
            else:
                # absent tracks do NOT consume an input index in _build_command
                for t in input.narration_tracks:
                    if t.exists():
                        narr_idx = idx
                        break
            if narr_idx is not None:
                audio_chain = (
                    f"[{narr_idx}:a]aformat=sample_fmts=fltp:"
                    f"channel_layouts=stereo[aout]"
                )
                return video_chain + audio_chain

        # Video-only graph
        return video_chain.rstrip(";")

    def _has_audio(self, clip_path: Path) -> bool:
        """True when the media file contains at least one audio stream."""
        try:
            proc = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-select_streams", "a",
                    "-show_entries", "stream=index",
                    "-of", "csv=p=0",
                    str(clip_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return bool(proc.stdout.strip())
        except Exception:
            return False

    def _build_xfade_chain(
        self, v_inputs: list[str], num_clips: int
    ) -> str:
        """Build an xfade chain for video crossfade transitions."""
        if num_clips < 2:
            return ""

        # Start with first two clips xfaded, then chain the rest
        chain = f"[{0}:v]scale={self.config.target_resolution[0]}:{self.config.target_resolution[1]}[v0];"
        chain += f"[{1}:v]scale={self.config.target_resolution[0]}:{self.config.target_resolution[1]}[v1];"
        chain += f"[v0][v1]xfade=transition=fade:duration={self.config.crossfade_duration}:offset=0[v01];"

        for i in range(2, num_clips):
            chain += f"[{i}:v]scale={self.config.target_resolution[0]}:{self.config.target_resolution[1]}[v{i}];"
            offset = (i - 1) * (6 - self.config.crossfade_duration)  # rough offset
            chain += f"[v01][v{i}]xfade=transition=fade:duration={self.config.crossfade_duration}:offset={offset}[v01];"

        chain = chain.replace("[v01]", "[vout]")
        return chain

    def _build_acrossfade_chain(
        self, a_inputs: list[str], num_clips: int
    ) -> str:
        """Build an acrossfade chain for audio crossfade transitions."""
        if num_clips < 2:
            return ""

        chain = f"[{0}:a]aformat=sample_fmts=fltp:channel_layouts=stereo[a0];"
        chain += f"[{1}:a]aformat=sample_fmts=fltp:channel_layouts=stereo[a1];"
        chain += f"[a0][a1]acrossfade=d={self.config.crossfade_duration}:c1=tri:c2=tri[a01];"

        for i in range(2, num_clips):
            chain += f"[{i}:a]aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}];"
            chain += f"[a01][a{i}]acrossfade=d={self.config.crossfade_duration}:c1=tri:c2=tri[a01];"

        chain = chain.replace("[a01]", "[aout]")
        return chain

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _timestamp() -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    @staticmethod
    def _probe_duration(path: Path) -> float:
        """Probe a video file for its duration using ffprobe."""
        try:
            proc = subprocess.run(
                [
                    "ffprobe",
                    "-v", "quiet",
                    "-print_format", "json",
                    "-show_format",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if proc.returncode != 0:
                return 0.0

            import json
            data = json.loads(proc.stdout)
            fmt = data.get("format", {})
            duration_str = fmt.get("duration", "0")
            return float(duration_str)
        except Exception:
            return 0.0
