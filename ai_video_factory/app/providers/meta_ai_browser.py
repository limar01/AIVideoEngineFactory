"""MetaAI Browser Provider — drives meta.ai Create interface via CDP/automation.

Auth model: no API keys. Meta session cookies (c_user, xs, etc.)
persist per-account. First login is manual (user logs into meta.ai in
a real browser); the session is then reused for automation. Never bypasses
CAPTCHA/2FA.

Generation flow (Create interface — deep search verified):
  1. Open meta.ai in browser, navigate to Create
  2. Select Video mode (not Image mode)
  3. Set aspect ratio (9:16 for Shorts/Reels)
  4. Set resolution (720p/1080p), aesthetic sliders (variety/weirdness/stylization)
  5. Type prompt → generates 4 variations
  6. Pick best → Custom Animate (motion prompt) → video
  7. Optionally: Extend, Music, Voiceover, Lip Sync
  8. Download MP4

Audio pipeline (separate — deep search verified):
  - Voice: Edge TTS (en-PH voices, unlimited, free, no signup)
  - Lip Sync: Meta AI built-in lip sync (feed Edge TTS audio)
  - SFX/Ambience: Freesound.org CC0
  - BGM: YouTube Audio Library
  - Mix/Assembly: FFMPEG

Reference:
  - meta.ai/ai-video-generator — Create interface
  - meta.com/help/.../1337455336906126 — Generate images and videos
  - meta.com/help/.../996454095987249 — Edit a video (Extend, Lip Sync, Music, Restyle)
  - github.com/mir-ashiq/meta-ai — CLI that reverse-engineers the API
  - felloai.com/meta-ai-video-generator — Movie Gen specs (1080p, 16s, 9:16)
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from app.providers.base import (
    GenerationCapabilities,
    GenerationResult,
    GenerationStatus,
    QuotaInfo,
    VideoGenerationProvider,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://meta.ai"
CREATE_URL = "https://meta.ai/create"  # or navigate via left menu "Create"

PROVIDER_NAME = "meta-ai-browser"

# Default download directory
DEFAULT_DOWNLOAD_DIR = os.path.expanduser("~/Data/meta-ai-downloads")

# Generation timeouts
DEFAULT_GENERATION_TIMEOUT_SECONDS = 600  # 10 minutes per generation
DEFAULT_POLL_INTERVAL_SECONDS = 10

# Aesthetic slider defaults (deep search verified — websensepro.com tutorial)
DEFAULT_VARIETY = 50      # 0-100 scale; 50 = detailed, clean
DEFAULT_WEIRDNESS = 0     # 0-100 scale; 0 = stable, realistic
DEFAULT_STYLIZATION = 200  # 0-1000 scale; ~200 = cinematic but not over-styled

# Supported options (deep search verified)
SUPPORTED_ASPECT_RATIOS = ["1:1", "9:16", "16:9"]
SUPPORTED_RESOLUTIONS = ["720p", "1080p"]
MAX_VIDEO_DURATION_SECONDS = 16  # Movie Gen limit (deep search verified)
MAX_EXTEND_COUNT = 5  # Can chain extends

# ---------------------------------------------------------------------------
# Meta AI Create interface selectors (to be live-probed)
# ---------------------------------------------------------------------------

# These are placeholder selectors — they need live probing on meta.ai
# The actual DOM structure will be discovered during first run

SEL_CREATE_BUTTON = "nav a[href*='create'], [data-testid='create-button']"
SEL_IMAGE_VIDEO_TOGGLE = "[data-testid='mode-toggle'], .mode-toggle"
SEL_VIDEO_MODE = "[data-testid='video-mode'], .mode-video"
SEL_ASPECT_RATIO_BTN = "[data-testid='aspect-ratio'], .aspect-ratio-btn"
SEL_ASPECT_VERTICAL = "[data-testid='aspect-9:16'], .aspect-vertical"
SEL_RESOLUTION_BTN = "[data-testid='resolution'], .resolution-btn"
SEL_RES_1080P = "[data-testid='res-1080p'], .res-1080p"
SEL_PROMPT_INPUT = "[data-testid='prompt-input'], textarea, input[type='text']"
SEL_GENERATE_BUTTON = "[data-testid='generate-button'], button:has-text('Generate')"
SEL_VARIATION_GRID = "[data-testid='variation-grid'], .variations"
SEL_VARIATION_ITEM = "[data-testid='variation-item'], .variation"
SEL_ANIMATE_BUTTON = "[data-testid='animate-button'], button:has-text('Animate')"
SEL_CUSTOM_ANIMATE = "[data-testid='custom-animate'], .custom-animate"
SEL_ANIMATION_PROMPT = "[data-testid='animation-prompt'], textarea"
SEL_EXTEND_BUTTON = "[data-testid='extend-button'], button:has-text('Extend')"
SEL_MUSIC_BUTTON = "[data-testid='music-button'], button:has-text('Music')"
SEL_VOICEOVER_BUTTON = "[data-testid='voiceover-button'], button:has-text('Voice')"
SEL_LIPSYNC_BUTTON = "[data-testid='lipsync-button'], button:has-text('Lip Sync')"
SEL_DOWNLOAD_BUTTON = "[data-testid='download-button'], button:has-text('Download')"
SEL_SAVE_BUTTON = "[data-testid='save-button'], button:has-text('Save')"

# Meta AI chat interface (alternative: generate via chat with @Meta AI)
SEL_CHAT_INPUT = "[data-testid='chat-input'], textarea"
SEL_SEND_BUTTON = "[data-testid='send-button'], button:has-text('Send')"
SEL_META_AI_CHAT = "[data-testid='meta-ai-chat'], a[href*='meta-ai']"

# ---------------------------------------------------------------------------
# Meta AI Video Provider
# ---------------------------------------------------------------------------


class MetaAIBrowserProvider(VideoGenerationProvider):
    """Video generation via Meta AI Create interface (browser automation).

    Uses CDP/Playwright to automate meta.ai's Create interface for
    image→animate→video workflow and direct video generation.

    Supported options (deep search verified):
      - aspect_ratios: 1:1, 9:16, 16:9
      - resolutions: 720p, 1080p
      - aesthetic sliders: variety (0-100), weirdness (0-100), stylization (0-1000)
      - image→animate: generate image first, then animate with motion prompt
      - custom animate: precise motion control via animation prompt
      - extend: chain clips (5s → 9s → 13s+)
      - music: add background music from Meta's library
      - voiceover/lip sync: add voice + sync to face
      - restyle: apply presets (anime, 3D, cyberpunk, etc.)

    Quota: Free tier (no hard limit discovered — appears unlimited for now).
    Follows provider rules — never bypasses CAPTCHA/2FA.
    """

    PROVIDER_NAME = PROVIDER_NAME

    def __init__(
        self,
        download_dir: Optional[str] = None,
        cookie_jar_path: Optional[str] = None,
        cdp_port: int = 9228,
    ):
        self.download_dir = Path(download_dir or DEFAULT_DOWNLOAD_DIR)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.cookie_jar_path = Path(cookie_jar_path or os.path.expanduser("~/.meta-ai-cookies.json"))
        self.cdp_port = cdp_port
        self._page = None  # Playwright page (set by orchestrator)
        self._cdp = None   # CDP connection (set by orchestrator)
        self._authenticated = False
        self._capabilities: Optional[GenerationCapabilities] = None

    # ------------------------------------------------------------------
    # VideoGenerationProvider interface
    # ------------------------------------------------------------------

    def authenticate(self, account_credentials: dict) -> bool:
        """Verify or establish authenticated Meta AI session.

        Loads stored session cookies. If session expired, returns False
        — does NOT attempt interactive login (CAPTCHA/2FA require user action).

        Args:
            account_credentials: dict with optional 'cookie_jar_path' override.

        Returns:
            True if session is valid, False if re-authentication needed.
        """
        jar_path = Path(account_credentials.get("cookie_jar_path", self.cookie_jar_path))
        if not jar_path.exists():
            logger.warning("No Meta AI cookie jar found at %s", jar_path)
            return False
        try:
            cookies = json.loads(jar_path.read_text())
            if not cookies:
                return False
            # Basic validation: check for required Meta cookies
            required = {"c_user", "xs"}
            cookie_names = {c.get("name") for c in cookies if isinstance(c, dict)}
            if required.issubset(cookie_names):
                self._authenticated = True
                logger.info("Meta AI session valid (cookies: %s)", list(cookie_names)[:5])
                return True
            logger.warning("Missing required Meta cookies: %s", required - cookie_names)
            return False
        except (json.JSONDecodeError, IOError) as e:
            logger.error("Failed to load cookie jar: %s", e)
            return False

    def check_session(self) -> bool:
        """Check whether current Meta AI session is still valid."""
        if not self._page and not self._cdp:
            return False
        # Try to access meta.ai and check for login redirect
        try:
            if self._page:
                self._page.goto(BASE_URL, timeout=10000, wait_until="domcontentloaded")
                # Check if we're logged in (no login wall)
                url = self._page.url
                if "login" in url.lower() or "facebook.com/login" in url:
                    return False
                return True
        except Exception as e:
            logger.debug("Session check failed: %s", e)
            return False
        return self._authenticated

    def get_capabilities(self) -> GenerationCapabilities:
        """Discover Meta AI provider capabilities."""
        if self._capabilities is None:
            self._capabilities = GenerationCapabilities(
                max_prompt_length=2000,  # Meta prompts can be detailed
                supported_aspect_ratios=list(SUPPORTED_ASPECT_RATIOS),
                supported_resolutions=list(SUPPORTED_RESOLUTIONS),
                max_duration_seconds=MAX_VIDEO_DURATION_SECONDS,
                min_duration_seconds=2.0,
                supports_narration=False,  # Meta generates video; audio is separate
            )
        return self._capabilities

    def get_quota(self) -> QuotaInfo:
        """Check current Meta AI quota/usage.

        Meta AI video generation appears to be free/unlimited as of 2026-09.
        Returns unknown quota — refinement needed after live probing.
        """
        return QuotaInfo(
            limit=None,     # Unlimited/free — exact limit unknown
            used=None,
            remaining=None,
            reset_time=None,
        )

    def submit_generation(
        self,
        prompt: str,
        scene_metadata: dict,
    ) -> GenerationResult:
        """Submit a Meta AI video generation request.

        Flow:
          1. Navigate to Create interface
          2. Set video mode, aspect ratio, resolution
          3. Set aesthetic sliders
          4. Enter prompt → generate 4 image variations
          5. Pick best variation → Custom Animate with motion prompt
          6. Return result ID for polling

        Args:
            prompt: Cinematic Filipino drama prompt (from Prompt Compiler).
            scene_metadata: dict with scene info:
                - aspect_ratio: "9:16" (default)
                - resolution: "1080p" (default)
                - variety: int (default 50)
                - weirdness: int (default 0)
                - stylization: int (default 200)
                - motion_prompt: str (custom animation description)
                - extend: int (extend count, default 0)
                - reference_image: Optional[str] (path to reference image)
                - generate_image_first: bool (default True — image→animate workflow)

        Returns:
            GenerationResult with result_id for polling, or error info.
        """
        caps = self.get_capabilities()

        # Extract scene options
        aspect_ratio = scene_metadata.get("aspect_ratio", "9:16")
        resolution = scene_metadata.get("resolution", "1080p")
        variety = scene_metadata.get("variety", DEFAULT_VARIETY)
        weirdness = scene_metadata.get("weirdness", DEFAULT_WEIRDNESS)
        stylization = scene_metadata.get("stylization", DEFAULT_STYLIZATION)
        motion_prompt = scene_metadata.get("motion_prompt", "")
        extend_count = scene_metadata.get("extend", 0)
        reference_image = scene_metadata.get("reference_image")
        generate_first = scene_metadata.get("generate_image_first", True)

        # Validate options
        if aspect_ratio not in SUPPORTED_ASPECT_RATIOS:
            return GenerationResult(
                success=False,
                error_code="INVALID_ASPECT_RATIO",
                error_message=f"Unsupported aspect ratio: {aspect_ratio}. Supported: {SUPPORTED_ASPECT_RATIOS}",
            )
        if resolution not in SUPPORTED_RESOLUTIONS:
            return GenerationResult(
                success=False,
                error_code="INVALID_RESOLUTION",
                error_message=f"Unsupported resolution: {resolution}. Supported: {SUPPORTED_RESOLUTIONS}",
            )
        if extend_count > MAX_EXTEND_COUNT:
            return GenerationResult(
                success=False,
                error_code="INVALID_EXTEND",
                error_message=f"Max extend count is {MAX_EXTEND_COUNT}, got {extend_count}",
            )

        # Build generation ID
        result_id = f"meta-ai-{int(time.time())}-{os.urandom(4).hex()}"

        logger.info(
            "Submitting Meta AI generation: id=%s, aspect=%s, res=%s, "
            "variety=%s, weirdness=%s, stylization=%s, extend=%s",
            result_id, aspect_ratio, resolution, variety, weirdness, stylization, extend_count,
        )

        # Check session
        if not self.check_session():
            return GenerationResult(
                success=False,
                error_code="SESSION_EXPIRED",
                error_message="Meta AI session expired — re-authentication required",
            )

        try:
            # The actual browser automation happens here.
            # This is a placeholder — the real implementation drives the
            # meta.ai Create interface via CDP/Playwright.
            #
            # Flow:
            #   1. self._page.goto(CREATE_URL)
            #   2. Click video mode toggle
            #   3. Set aspect ratio dropdown to 9:16
            #   4. Set resolution to 1080p
            #   5. Set aesthetic sliders (variety=50, weirdness=0, stylization=200)
            #   6. Type prompt into prompt input
            #   7. Click Generate → wait for 4 image variations
            #   8. Click best variation → Custom Animate
            #   9. Type motion prompt → Animate → wait for video
            #  10. If extend > 0: click Extend → wait → repeat
            #  11. Download MP4

            # For now, return a mock result that the orchestrator can poll.
            # In production, replace with actual browser automation.
            generation_id = f"gen-{result_id}"

            logger.info(
                "Generation submitted (simulated): %s — prompt length=%d",
                generation_id, len(prompt),
            )

            return GenerationResult(
                success=True,
                result_id=generation_id,
                estimated_wait_seconds=120,  # ~2 minutes typical
            )

        except Exception as e:
            logger.error("Generation submission failed: %s", e)
            return GenerationResult(
                success=False,
                error_code="SUBMISSION_ERROR",
                error_message=str(e),
            )

    def get_generation_status(self, result_id: str) -> GenerationStatus:
        """Poll for the status of a submitted Meta AI generation.

        Args:
            result_id: The result_id returned by submit_generation.

        Returns:
            Current generation status.
        """
        # Placeholder — real implementation polls the meta.ai generation
        # status via browser automation or API.
        #
        # Flow:
        #   1. Navigate to Meta AI media gallery
        #   2. Find generation by result_id
        #   3. Check if video is ready (downloaded/available)
        #   4. Return appropriate status

        # Simulate: after 2 minutes, mark as completed
        # In production, replace with actual polling
        logger.debug("Polling status for: %s", result_id)
        return GenerationStatus.UNKNOWN

    def download_result(self, result_id: str) -> bytes:
        """Download a completed Meta AI generation result.

        Args:
            result_id: The result_id returned by submit_generation.

        Returns:
            Raw bytes of the generated video (MP4).
        """
        # Placeholder — real implementation:
        #   1. Navigate to generated video in Meta AI
        #   2. Click Download button
        #   3. Wait for download to complete
        #   4. Read file from download dir
        #   5. Return bytes

        download_path = self.download_dir / f"{result_id}.mp4"
        if download_path.exists():
            return download_path.read_bytes()

        raise FileNotFoundError(f"Generation result not found: {result_id}")

    def detect_error(
        self,
        result_id: str,
        raw_response: str,
    ) -> tuple[Optional[str], Optional[str]]:
        """Parse a raw response and extract error info.

        Args:
            result_id: The generation result ID.
            raw_response: Raw response text from the generation.

        Returns:
            (error_code, error_message) or (None, None) if no error.
        """
        # Check for common Meta AI errors
        error_patterns = [
            (r"not available", "NOT_AVAILABLE"),
            (r"try again later", "RATE_LIMITED"),
            (r"something went wrong", "GENERATION_ERROR"),
            (r"no images generated", "NO_OUTPUT"),
            (r"content policy", "POLICY_VIOLATION"),
        ]

        for pattern, code in error_patterns:
            if re.search(pattern, raw_response, re.IGNORECASE):
                return (code, raw_response[:200])

        return (None, None)

    def detect_quota_exhaustion(self, raw_response: str) -> bool:
        """Determine if the raw response indicates quota/rate-limit exhaustion."""
        quota_patterns = [
            r"out of (generations|credits|quota)",
            r"(daily|weekly) (limit|cap) (reached|exceeded)",
            r"try again (tomorrow|later|in \d+ hours)",
            r"rate limit",
        ]
        for pattern in quota_patterns:
            if re.search(pattern, raw_response, re.IGNORECASE):
                return True
        return False

    def close_session(self) -> None:
        """Cleanly close the Meta AI provider session."""
        self._authenticated = False
        self._page = None
        self._cdp = None
        logger.info("Meta AI session closed")
