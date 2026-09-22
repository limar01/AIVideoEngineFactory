"""Clip downloader — downloads generated clips from providers to the local clips directory.

Source: docs/ARCHITECTURE.md §4.11 (downloader/), Master Spec §16 (download pipeline)

Abstracts the download step so the queue/assembly layers don't need provider-specific
download logic.  Each provider exposes ``download_result(result_id) -> bytes``.
This module wraps that into:
1. Download raw bytes
2. Validate the result is non-empty
3. Write to the project clips directory with a deterministic filename
4. Return the local Path for assembly/QA

All downloads go through ``QUOTA.md`` §4 (Authorized Account Pool) — never bypass
rate limits or quotas.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from app.providers.base import VideoGenerationProvider, GenerationResult, GenerationStatus

logger = logging.getLogger(__name__)

# Default clips directory (relative to project root)
DEFAULT_CLIPS_DIR = Path("clips")


class ClipDownloadError(Exception):
    """Raised when a clip download fails for any reason."""

    def __init__(self, result_id: str, provider: str, reason: str) -> None:
        self.result_id = result_id
        self.provider = provider
        self.reason = reason
        super().__init__(f"Download failed [{provider}] {result_id}: {reason}")


class ClipDownloader:
    """Downloads clips from a provider and stores them locally.

    Thread-unsafe — instantiate one per worker or protect with a lock.
    """

    def __init__(
        self,
        provider: VideoGenerationProvider,
        clips_dir: str | Path = DEFAULT_CLIPS_DIR,
        overwrite: bool = False,
    ) -> None:
        self.provider = provider
        self.clips_dir = Path(clips_dir)
        self.overwrite = overwrite
        self.clips_dir.mkdir(parents=True, exist_ok=True)

        # Track downloaded clips: result_id -> local path
        self._downloaded: dict[str, Path] = {}

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def download(
        self,
        result_id: str,
        *,
        filename: str | None = None,
        description: str = "",
    ) -> Path:
        """Download a completed clip from the provider to the local clips dir.

        Args:
            result_id: The generation result ID (from submit_generation).
            filename: Optional custom filename (without extension). If None,
                      derives a name from ``result_id``.
            description: Human-readable description for log messages.

        Returns:
            Path to the downloaded MP4 file.

        Raises:
            ClipDownloadError: If the download fails or the file is empty.
        """
        if result_id in self._downloaded:
            logger.info("ClipDownloader.download — already downloaded %s", result_id)
            return self._downloaded[result_id]

        # Check status first
        status = self.provider.get_generation_status(result_id)
        if status != GenerationStatus.COMPLETED:
            raise ClipDownloadError(
                result_id,
                self.provider.PROVIDER_NAME,
                f"Status is {status.value}, not COMPLETED",
            )

        desc = description or result_id[:8]
        stem = filename or f"clip_{result_id[:8]}"
        dest = self.clips_dir / f"{stem}.mp4"

        if dest.exists() and not self.overwrite:
            logger.warning(
                "ClipDownloader.download — %s already exists, skipping (set overwrite=True to replace)",
                dest,
            )
            self._downloaded[result_id] = dest
            return dest

        logger.info("ClipDownloader.download — downloading %s -> %s", result_id, dest)

        try:
            raw_bytes = self.provider.download_result(result_id)
        except Exception as exc:
            raise ClipDownloadError(
                result_id,
                self.provider.PROVIDER_NAME,
                f"Provider download failed: {exc}",
            ) from exc

        if not raw_bytes:
            raise ClipDownloadError(
                result_id,
                self.provider.PROVIDER_NAME,
                "Downloaded bytes are empty",
            )

        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw_bytes)

        logger.info(
            "ClipDownloader.download — saved %d bytes to %s (%s)",
            len(raw_bytes),
            dest,
            desc,
        )

        self._downloaded[result_id] = dest
        return dest

    def download_and_move(
        self,
        result_id: str,
        *,
        filename: str | None = None,
        description: str = "",
        dest_dir: str | Path | None = None,
    ) -> Path:
        """Download a clip and move it to an arbitrary destination directory.

        Convenience wrapper around ``download()`` + ``shutil.move()``.
        """
        clip_path = self.download(result_id, filename=filename, description=description)

        if dest_dir is None:
            return clip_path

        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)

        dest = dest_dir / clip_path.name
        if dest.exists() and not self.overwrite:
            return dest

        shutil.move(str(clip_path), str(dest))
        logger.info("ClipDownloader.download_and_move — moved %s -> %s", clip_path, dest)
        return dest

    # ------------------------------------------------------------------
    # Listing / cleanup
    # ------------------------------------------------------------------

    def list_downloaded(self) -> list[Path]:
        """Return all locally downloaded clips."""
        return list(self._downloaded.values())

    def clear_cache(self) -> None:
        """Clear the in-memory download cache (does NOT delete files)."""
        self._downloaded.clear()

    def cleanup(self) -> None:
        """Close the provider session (calls provider.close_session())."""
        self.provider.close_session()
        logger.info("ClipDownloader.cleanup — provider session closed")
