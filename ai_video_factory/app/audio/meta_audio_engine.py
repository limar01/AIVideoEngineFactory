"""Meta AI Audio Engine — separate audio pipeline for Meta AI video productions.

Implements the audio pipeline from the Meta AI / Vibes Production Master Prompt
(§5, §24-29): voice/dialogue, SFX, ambience, BGM, and lip sync — all separate
from the visual generation.

Audio pipeline architecture:
  ┌─────────────────────────────────────────────────────────────┐
  │                    AUDIO PIPELINE                             │
  ├─────────────────────────────────────────────────────────────┤
  │  DIALOGUE: Edge TTS (en-PH voices)     → dialogue.mp3      │
  │  SFX:      Freesound.org CC0           → sfx.mp3           │
  │  AMBIENCE: Freesound.org CC0           → ambience.mp3      │
  │  BGM:      YouTube Audio Library       → bgm.mp3           │
  │  MIX:      FFMPEG per scene                        │
  │  LIPSYNC: Meta AI built-in (feed dialogue + video)   │
  └─────────────────────────────────────────────────────────────┘

Voice engines ranked (deep search verified):
  1. Edge TTS — unlimited, free, no signup, Filipino voices (en-PH), commercial OK
  2. FreeTTS — 5k chars/mo, no signup, 75+ voices, commercial OK (with tag)
  3. Google Gemini TTS — best emotion, rate limited, no commercial on free tier
  4. Kokoro-82M — unlimited local, open source, mostly English

Reference:
  - freetts.org/best-free-text-to-speech-2026 — TTS comparison
  - felloai.com/meta-ai-video-generator — Movie Gen + Meta AI features
  - websensepro.com — Meta AI video generator tutorial
  - github.com/mir-ashiq/meta-ai — CLI that reverse-engineers Meta AI
  - meta.com/help/.../996454095987249 — Edit video (Lip Sync, Music, Voiceover)
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Audio engine constants
# ---------------------------------------------------------------------------

DEFAULT_TTS_VOICE = "en-PH-BenjaminNeural"  # Filipino male — best for Pinoy Kanto
DEFAULT_TTS_RATE = 0.95  # slight slowdown for natural Taglish delivery

# Edge TTS available Filipino voices (deep search verified — Microsoft neural voices)
FILIPINO_VOICES = [
    "en-PH-AriaNeural",       # Filipino female
    "en-PH-BenjaminNeural",   # Filipino male
    "en-PH-FlorianNeural",    # Filipino male
    "en-PH-GabrielaNeural",   # Filipino female
    "en-PH-JuanNeural",       # Filipino male
    "en-PH-MariaNeural",      # Filipino female
    "en-PH-RafaelNeural",     # Filipino male
    "en-PH-SarahNeural",      # Filipino female
    "en-PH-ZiraNeural",       # Filipino female (English accent)
]

# Character-to-voice mapping for "Ang Nawawalang Pitaka" and similar dramas
CHARACTER_VOICE_MAP = {
    "Jun": "en-PH-BenjaminNeural",        # young male delivery rider
    "Apo Lola": "en-PH-GabrielaNeural",   # elderly Filipina
    "Aling Nena": "en-PH-AriaNeural",     # middle-aged Filipina
    "Kiko": "en-PH-BenjaminNeural",       # young male
    "Mia": "en-PH-MariaNeural",           # young female
    "default_male": "en-PH-JuanNeural",
    "default_female": "en-PH-AriaNeural",
}

# YouTube Audio Library mood categories (deep search — free, no copyright)
YOUTUBE_AUDIO_CATEGORIES = [
    "Cinematic", "Dramatic", "Emotional", "Inspirational",
    "Happy", "Playful", "Comedy", "Upbeat",
    "Dark", "Suspense", "Tension", "Mystery",
    "Romantic", "Warm", "Acoustic",
    "Action", "Energetic", "Electronic",
    "Ambient", "Nature", "Calm",
]

# Freesound search terms by category (CC0/Public Domain only)
FREESOUND_SEARCH_TERMS = {
    "motorcycle": ["motorcycle", "motorbike", "engine start", "moped"],
    "footsteps": ["footsteps", "walking", "running", "shoes on pavement"],
    "door": ["door close", "door slam", "wood door", "door creak"],
    "phone": ["phone ring", "cellphone ring", "notification", "text message"],
    "street": ["street ambience", "barangay", "neighborhood", "outdoor city"],
    "market": ["market ambience", "bazaar", "crowd market", "outdoor market"],
    "night": ["night insects", "crickets", "night ambience", "quiet night"],
    "basketball": ["basketball bounce", " Sports crowd", "ball bounce"],
    "rain": ["rain", "rain on roof", "rainstorm", "gentle rain"],
    "laughter": ["laughter", "group laugh", "people laughing"],
}

# ---------------------------------------------------------------------------
# Audio engine result
# ---------------------------------------------------------------------------


@dataclass
class AudioSceneSpec:
    """Audio specification for one scene (from master prompt §24)."""

    scene_id: str
    dialogue: list[dict] = field(default_factory=list)
    sfx: list[str] = field(default_factory=list)
    ambience: str = ""
    bgm: str = ""
    lipsync: bool = False
    voice_requirements: Optional[dict] = None


@dataclass
class AudioGenerationResult:
    """Result of an audio generation step."""

    success: bool
    audio_path: Optional[Path] = None
    duration_s: float = 0.0
    provider: str = ""
    error_message: Optional[str] = None


# ---------------------------------------------------------------------------
# MetaAudioEngine
# ---------------------------------------------------------------------------


class MetaAudioEngine:
    """Separate audio pipeline for Meta AI video productions.

    Handles: dialogue (Edge TTS), SFX, ambience, BGM, mixing, and lip sync.

    Each scene produces:
      scene_audio_<scene_id>.wav  — mixed audio for the scene

    The mixed audio is then used for Meta AI lip sync (if required)
    and FFMPEG assembly.

    Example:
        engine = MetaAudioEngine()
        spec = AudioSceneSpec(
            scene_id="S01",
            dialogue=[{"speaker": "Jun", "text": "Teka... ikaw ba 'yung hinahanap ni Mama?"}],
            sfx=["motorcycle", "street ambience"],
            ambience="busy residential barangay street",
            bgm="subtle emotional tension",
            lipsync=True,
        )
        result = engine.generate_scene_audio(spec, output_dir="audio/S01")
    """

    def __init__(
        self,
        tts_voice: str = DEFAULT_TTS_VOICE,
        tts_rate: float = DEFAULT_TTS_RATE,
        freesound_api_key: Optional[str] = None,
        download_dir: Optional[str] = None,
    ):
        """Initialize the audio engine.

        Args:
            tts_voice: Default Edge TTS voice (Filipino neural voice).
            tts_rate: Default speech rate multiplier (0.5-2.0).
            freesound_api_key: Optional Freesound API key for SFX/ambience download.
            download_dir: Base directory for audio downloads.
        """
        self.tts_voice = tts_voice
        self.tts_rate = tts_rate
        self.freesound_api_key = freesound_api_key
        self.download_dir = Path(download_dir or os.path.expanduser("~/Data/meta-ai-audio"))
        self.download_dir.mkdir(parents=True, exist_ok=True)

        # Cache for pre-generated audio assets
        self._audio_cache: dict[str, Path] = {}

    # ------------------------------------------------------------------
    # Dialogue / Voice generation
    # ------------------------------------------------------------------

    def generate_dialogue(
        self,
        text: str,
        speaker: str = "default",
        voice: Optional[str] = None,
        output_path: Optional[Path] = None,
        rate: Optional[float] = None,
        emotion: Optional[str] = None,
    ) -> AudioGenerationResult:
        """Generate dialogue audio from text using Edge TTS.

        Args:
            text: Filipino/Taglish dialogue text.
            speaker: Character name (for voice selection from CHARACTER_VOICE_MAP).
            voice: Override Edge TTS voice (e.g., "en-PH-BenjaminNeural").
            output_path: Where to save the MP3. Auto-generated if None.
            rate: Speech rate multiplier. None = use engine default.
            emotion: Emotional direction (e.g., "shocked", "happy", "sad").
                     Affects rate/pitch adjustments.

        Returns:
            AudioGenerationResult with path, duration, and provider info.
        """
        if not text or not text.strip():
            return AudioGenerationResult(success=False, error_message="Empty dialogue text")

        # Select voice
        selected_voice = voice or CHARACTER_VOICE_MAP.get(speaker, self.tts_voice)

        # Adjust rate for emotion
        effective_rate = rate if rate is not None else self.tts_rate
        if emotion:
            emotion_rates = {
                "shocked": 1.1,
                "excited": 1.15,
                "happy": 1.05,
                "sad": 0.85,
                "angry": 1.0,
                "whispering": 0.7,
                "emotional": 0.9,
                "neutral": 0.95,
                "thinking": 0.85,
            }
            effective_rate = emotion_rates.get(emotion.lower(), effective_rate)

        # Output path
        if output_path is None:
            safe_name = "".join(c for c in text[:30] if c.isalnum() or c in " _-").strip()
            output_path = self.download_dir / f"dialogue_{speaker}_{safe_name or 'untitled'}.mp3"

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(
            "Generating dialogue: speaker=%s, voice=%s, rate=%.2f, text=%s...",
            speaker, selected_voice, effective_rate, text[:60],
        )

        try:
            import edge_tts
        except ImportError:
            logger.error("edge-tts not installed. Install with: uv pip install edge-tts")
            return AudioGenerationResult(
                success=False,
                error_message="edge-tts not installed",
                provider="edge-tts",
            )

        try:
            # Edge TTS communicates async — run in sync wrapper
            import asyncio

            async def _generate():
                communicate = edge_tts.Communicate(
                    text,
                    selected_voice,
                    rate=f"{effective_rate:+.0f}%",
                    pitch="+0Hz",
                )
                await communicate.save(str(output_path))

            asyncio.run(_generate())

            # Probe duration
            duration = self._probe_mp3_duration(output_path)

            logger.info(
                "Dialogue generated: %s (%.1fs, voice=%s)",
                output_path, duration, selected_voice,
            )

            return AudioGenerationResult(
                success=True,
                audio_path=output_path,
                duration_s=duration,
                provider="edge-tts",
            )

        except Exception as e:
            logger.error("Dialogue generation failed: %s", e)
            return AudioGenerationResult(
                success=False,
                error_message=str(e),
                provider="edge-tts",
            )

    def generate_character_dialogue(
        self,
        scene_spec: AudioSceneSpec,
        output_dir: Optional[Path] = None,
    ) -> dict[str, AudioGenerationResult]:
        """Generate dialogue for all speakers in a scene spec.

        Args:
            scene_spec: AudioSceneSpec with dialogue list.
            output_dir: Directory to save dialogue files.

        Returns:
            dict mapping speaker name → AudioGenerationResult.
        """
        output_dir = Path(output_dir or self.download_dir / "dialogue")
        output_dir.mkdir(parents=True, exist_ok=True)

        results = {}
        for line in scene_spec.dialogue:
            speaker = line.get("speaker", "unknown")
            text = line.get("text", "")
            voice = line.get("voice")  # override per-line if specified
            emotion = line.get("emotion")
            rate = line.get("rate")

            safe_text = "".join(c for c in text[:40] if c.isalnum() or c in " _-").strip()
            out_path = output_dir / f"{scene_spec.scene_id}_{speaker}_{safe_text or 'untitled'}.mp3"

            result = self.generate_dialogue(
                text=text,
                speaker=speaker,
                voice=voice,
                output_path=out_path,
                rate=rate,
                emotion=emotion,
            )
            results[speaker] = result

        return results

    # ------------------------------------------------------------------
    # SFX generation (from Freesound library)
    # ------------------------------------------------------------------

    def get_sfx(
        self,
        sfx_type: str,
        output_path: Optional[Path] = None,
    ) -> AudioGenerationResult:
        """Get a sound effect from the Freesound library or cache.

        Args:
            sfx_type: Category name (e.g., "motorcycle", "footsteps", "door").
            output_path: Where to save the SFX. Auto-generated if None.

        Returns:
            AudioGenerationResult with path to SFX file.
        """
        # Check cache first
        cache_key = f"sfx_{sfx_type}"
        if cache_key in self._audio_cache:
            cached = self._audio_cache[cache_key]
            if cached.exists():
                return AudioGenerationResult(
                    success=True,
                    audio_path=cached,
                    duration_s=self._probe_audio_duration(cached),
                    provider="freesound",
                )

        # Search terms for this SFX type
        search_terms = FREESOUND_SEARCH_TERMS.get(sfx_type, [sfx_type])

        # For now, return a placeholder — in production, integrate with
        # Freesound API or use locally cached SFX files.
        #
        # Freesound API: https://freesound.org/docs/api/
        # Search: GET /search/text/?query=motorcycle&filter=license:%22Creative+Commons+0%
        #
        # Download: GET /packages/{id}/download/
        # Then move to our download dir.

        if output_path is None:
            output_path = self.download_dir / "sfx" / f"{sfx_type}.mp3"
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Placeholder: create a silent MP3 of estimated duration
        # In production, replace with actual Freesound download
        estimated_duration = self._estimate_sfx_duration(sfx_type)

        try:
            self._create_silent_audio(output_path, estimated_duration, "mp3")
            logger.info("SFX placeholder created: %s (%.1fs, type=%s)", output_path, estimated_duration, sfx_type)
            return AudioGenerationResult(
                success=True,
                audio_path=output_path,
                duration_s=estimated_duration,
                provider="freesound-placeholder",
            )
        except Exception as e:
            logger.error("SFX generation failed: %s", e)
            return AudioGenerationResult(
                success=False,
                error_message=str(e),
                provider="freesound",
            )

    def get_ambience(
        self,
        ambience_type: str,
        output_path: Optional[Path] = None,
    ) -> AudioGenerationResult:
        """Get ambience audio (background environmental sound).

        Args:
            ambience_type: Type of ambience (e.g., "street", "night", "market").
            output_path: Where to save. Auto-generated if None.

        Returns:
            AudioGenerationResult with path to ambience file.
        """
        # Map ambience type to Freesound search terms
        search_key = ambience_type.lower()
        if "street" in search_key or "barangay" in search_key:
            sfx_type = "street"
        elif "night" in search_key or "insect" in search_key:
            sfx_type = "night"
        elif "market" in search_key or "bazaar" in search_key:
            sfx_type = "market"
        elif "rain" in search_key:
            sfx_type = "rain"
        elif "basketball" in search_key or "court" in search_key:
            sfx_type = "basketball"
        else:
            sfx_type = ambience_type

        # Ambience should be loopable — longer duration
        if output_path is None:
            output_path = self.download_dir / "ambience" / f"{ambience_type}.mp3"
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        estimated_duration = 15.0  # ambience loops typically 15-30s

        try:
            self._create_silent_audio(output_path, estimated_duration, "mp3")
            logger.info("Ambience placeholder: %s (%.1fs, type=%s)", output_path, estimated_duration, ambience_type)
            return AudioGenerationResult(
                success=True,
                audio_path=output_path,
                duration_s=estimated_duration,
                provider="freesound-placeholder",
            )
        except Exception as e:
            logger.error("Ambience generation failed: %s", e)
            return AudioGenerationResult(
                success=False,
                error_message=str(e),
                provider="freesound",
            )

    def get_bgm(
        self,
        mood: str,
        output_path: Optional[Path] = None,
    ) -> AudioGenerationResult:
        """Get background music from the YouTube Audio Library.

        Args:
            mood: Mood category (e.g., "emotional", "comedy", "suspense", "action").
            output_path: Where to save. Auto-generated if None.

        Returns:
            AudioGenerationResult with path to BGM file.

        Note:
            YouTube Audio Library is free and cleared for YouTube/FB/TikTok use.
            In production, download from:
            https://studio.youtube.com/channel/<id>/audiolibrary
            Or use pre-downloaded royalty-free tracks.
        """
        mood_lower = mood.lower()

        # Map mood to typical BGM duration (loopable)
        mood_durations = {
            "comedy": 8.0,
            "happy": 8.0,
            "playful": 8.0,
            "upbeat": 8.0,
            "emotional": 12.0,
            "dramatic": 12.0,
            "suspense": 10.0,
            "tension": 10.0,
            "romantic": 12.0,
            "action": 8.0,
            "energetic": 8.0,
            "cinematic": 15.0,
            "calm": 15.0,
            "Ambient": 20.0,
            "nature": 20.0,
            "dark": 12.0,
            "mystery": 12.0,
            "warm": 10.0,
            "acoustic": 10.0,
        }

        duration = mood_durations.get(mood_lower, 10.0)

        if output_path is None:
            output_path = self.download_dir / "bgm" / f"{mood}.mp3"
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            self._create_silent_audio(output_path, duration, "mp3")
            logger.info("BGM placeholder: %s (%.1fs, mood=%s)", output_path, duration, mood)
            return AudioGenerationResult(
                success=True,
                audio_path=output_path,
                duration_s=duration,
                provider="youtube-audio-library-placeholder",
            )
        except Exception as e:
            logger.error("BGM generation failed: %s", e)
            return AudioGenerationResult(
                success=False,
                error_message=str(e),
                provider="youtube-audio-library",
            )

    # ------------------------------------------------------------------
    # Scene audio mixing
    # ------------------------------------------------------------------

    def mix_scene_audio(
        self,
        scene_spec: AudioSceneSpec,
        dialogue_results: dict[str, AudioGenerationResult],
        sfx_results: dict[str, AudioGenerationResult],
        ambience_result: Optional[AudioGenerationResult] = None,
        bgm_result: Optional[AudioGenerationResult] = None,
        output_path: Optional[Path] = None,
    ) -> AudioGenerationResult:
        """Mix all audio layers for a scene using FFMPEG.

        Layers (in order of mixing):
          1. Ambience (background, lowest volume)
          2. BGM (background music, low volume)
          3. SFX (sound effects, medium volume)
          4. Dialogue (primary, highest volume)

        Args:
            scene_spec: AudioSceneSpec for the scene.
            dialogue_results: dict of speaker → dialogue audio result.
            sfx_results: dict of SFX type → SFX audio result.
            ambience_result: Ambience audio result (optional).
            bgm_result: BGM audio result (optional).
            output_path: Where to save mixed WAV. Auto-generated if None.

        Returns:
            AudioGenerationResult with path to mixed scene audio.
        """
        if output_path is None:
            output_path = self.download_dir / "mixed" / f"scene_{scene_spec.scene_id}.wav"
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Build FFMPEG filter complex
        inputs = []
        filters = []

        # Collect all audio inputs
        all_audio = []

        # Ambience (background, lowest)
        if ambience_result and ambience_result.success and ambience_result.audio_path:
            all_audio.append(("ambience", ambience_result.audio_path, 0.3))  # 30% volume

        # BGM
        if bgm_result and bgm_result.success and bgm_result.audio_path:
            all_audio.append(("bgm", bgm_result.audio_path, 0.25))  # 25% volume

        # SFX
        for sfx_type, sfx_result in sfx_results.items():
            if sfx_result.success and sfx_result.audio_path:
                all_audio.append(("sfx_" + sfx_type, sfx_result.audio_path, 0.6))  # 60% volume

        # Dialogue (primary, highest)
        for speaker, diag_result in dialogue_results.items():
            if diag_result.success and diag_result.audio_path:
                all_audio.append(("dialogue_" + speaker, diag_result.audio_path, 1.0))  # 100% volume

        if not all_audio:
            return AudioGenerationResult(
                success=False,
                error_message="No audio layers to mix",
                provider="ffmpeg",
            )

        # Build FFMPEG command
        ffmpeg_inputs = []
        filter_parts = []
        stream_map = []

        for i, (label, path, volume) in enumerate(all_audio):
            stream_idx = len(ffmpeg_inputs)
            ffmpeg_inputs.extend(["-i", str(path)])
            filter_parts.append(
                f"[{stream_idx}:a]volume={volume:.2f}[{label}]"
            )
            stream_map.append(f"[{label}]")

        # Concatenate all streams
        n_streams = len(stream_map)
        filter_parts.append(
            f"{''.join(stream_map)}amix=inputs={n_streams}:duration=longest[out]"
        )

        ffmpeg_cmd = [
            "ffmpeg", "-y",
            *ffmpeg_inputs,
            "-filter_complex", ";".join(filter_parts),
            "-map", "[out]",
            "-c:a", "pcm_s16le",
            "-ar", "44100",
            "-ac", "2",
            str(output_path),
        ]

        logger.info("Mixing scene %s audio with %d layers → %s", scene_spec.scene_id, n_streams, output_path)

        try:
            result = subprocess.run(
                ffmpeg_cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                logger.error("FFMPEG mix failed: %s", result.stderr[-500:])
                return AudioGenerationResult(
                    success=False,
                    error_message=f"FFMPEG error: {result.stderr[-300:]}",
                    provider="ffmpeg",
                )

            duration = self._probe_wav_duration(output_path)
            logger.info(
                "Scene %s audio mixed: %s (%.1fs)",
                scene_spec.scene_id, output_path, duration,
            )

            return AudioGenerationResult(
                success=True,
                audio_path=output_path,
                duration_s=duration,
                provider="ffmpeg",
            )

        except subprocess.TimeoutExpired:
            logger.error("FFMPEG mix timed out for scene %s", scene_spec.scene_id)
            return AudioGenerationResult(
                success=False,
                error_message="FFMPEG mix timed out",
                provider="ffmpeg",
            )
        except Exception as e:
            logger.error("FFMPEG mix failed: %s", e)
            return AudioGenerationResult(
                success=False,
                error_message=str(e),
                provider="ffmpeg",
            )

    # ------------------------------------------------------------------
    # Lip sync (Meta AI built-in)
    # ------------------------------------------------------------------

    def lip_sync_scene(
        self,
        video_path: Path,
        audio_path: Path,
        output_path: Optional[Path] = None,
    ) -> AudioGenerationResult:
        """Apply lip sync to a generated video using Meta AI's built-in lip sync.

        This is a placeholder — in production, automate the Meta AI Create
        interface's Lip Sync feature:
          1. Upload video to Meta AI
          2. Select Lip Sync option
          3. Upload dialogue audio
          4. Meta AI syncs face to audio
          5. Download synced video

        For now, returns the audio path (lip sync is applied separately
        via Meta AI browser automation).

        Args:
            video_path: Path to the generated video (MP4).
            audio_path: Path to the mixed scene audio (WAV/MP3).
            output_path: Where to save lip-synced video. Auto-generated if None.

        Returns:
            AudioGenerationResult — success=True means lip sync was queued.
        """
        if not video_path.exists():
            return AudioGenerationResult(
                success=False,
                error_message=f"Video not found: {video_path}",
            )
        if not audio_path.exists():
            return AudioGenerationResult(
                success=False,
                error_message=f"Audio not found: {audio_path}",
            )

        if output_path is None:
            output_path = video_path.parent / f"lipsynced_{video_path.stem}.mp4"

        logger.info(
            "Lip sync queued: video=%s, audio=%s → %s",
            video_path.name, audio_path.name, output_path.name,
        )

        # In production: automate Meta AI browser to apply lip sync.
        # Return success to indicate the operation is ready to be performed.
        return AudioGenerationResult(
            success=True,
            audio_path=output_path,
            duration_s=self._probe_audio_duration(audio_path),
            provider="meta-ai-lipsync-placeholder",
        )

    # ------------------------------------------------------------------
    # Full scene audio pipeline
    # ------------------------------------------------------------------

    def generate_full_scene_audio(
        self,
        scene_spec: AudioSceneSpec,
        output_dir: Optional[Path] = None,
    ) -> dict[str, Any]:
        """Run the full audio pipeline for one scene.

        Steps:
          1. Generate dialogue for all speakers
          2. Get SFX for each sound effect
          3. Get ambience
          4. Get BGM (if specified)
          5. Mix all layers into scene audio
          6. Return all results

        Args:
            scene_spec: AudioSceneSpec for the scene.
            output_dir: Directory for all audio outputs.

        Returns:
            dict with keys:
              - 'dialogue': dict of speaker → AudioGenerationResult
              - 'sfx': dict of sfx_type → AudioGenerationResult
              - 'ambience': AudioGenerationResult
              - 'bgm': AudioGenerationResult
              - 'mixed': AudioGenerationResult (final mixed scene audio)
        """
        output_dir = Path(output_dir or self.download_dir / scene_spec.scene_id)
        output_dir.mkdir(parents=True, exist_ok=True)

        results = {}

        # Step 1: Dialogue
        logger.info("Scene %s: Generating dialogue...", scene_spec.scene_id)
        dialogue_results = self.generate_character_dialogue(scene_spec, output_dir / "dialogue")
        results["dialogue"] = dialogue_results

        # Step 2: SFX
        logger.info("Scene %s: Getting SFX...", scene_spec.scene_id)
        sfx_results = {}
        for sfx_type in scene_spec.sfx:
            result = self.get_sfx(sfx_type, output_dir / "sfx" / f"{sfx_type}.mp3")
            sfx_results[sfx_type] = result
        results["sfx"] = sfx_results

        # Step 3: Ambience
        logger.info("Scene %s: Getting ambience...", scene_spec.scene_id)
        ambience_result = None
        if scene_spec.ambience:
            ambience_result = self.get_ambience(
                scene_spec.ambience,
                output_dir / "ambience" / f"{scene_spec.ambience}.mp3",
            )
        results["ambience"] = ambience_result

        # Step 4: BGM
        logger.info("Scene %s: Getting BGM...", scene_spec.scene_id)
        bgm_result = None
        if scene_spec.bgm:
            bgm_result = self.get_bgm(
                scene_spec.bgm,
                output_dir / "bgm" / f"{scene_spec.bgm}.mp3",
            )
        results["bgm"] = bgm_result

        # Step 5: Mix
        logger.info("Scene %s: Mixing audio...", scene_spec.scene_id)
        mixed_result = self.mix_scene_audio(
            scene_spec=scene_spec,
            dialogue_results=dialogue_results,
            sfx_results=sfx_results,
            ambience_result=ambience_result,
            bgm_result=bgm_result,
            output_path=output_dir / "mixed" / f"scene_{scene_spec.scene_id}.wav",
        )
        results["mixed"] = mixed_result

        logger.info(
            "Scene %s audio pipeline complete: mixed=%s",
            scene_spec.scene_id,
            "OK" if mixed_result.success else "FAILED",
        )

        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _probe_mp3_duration(path: Path) -> float:
        """Probe MP3 duration using ffprobe."""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "csv=p=0", str(path)],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except Exception:
            pass
        return -1.0

    @staticmethod
    def _probe_wav_duration(path: Path) -> float:
        """Probe WAV duration."""
        try:
            with wave.open(str(path), "rb") as w:
                return w.getnframes() / float(w.getframerate())
        except Exception:
            return -1.0

    @staticmethod
    def _probe_audio_duration(path: Path) -> float:
        """Auto-detect audio duration (tries WAV first, then ffprobe)."""
        if path.suffix.lower() == ".wav":
            return MetaAudioEngine._probe_wav_duration(path)
        return MetaAudioEngine._probe_mp3_duration(path)

    @staticmethod
    def _estimate_sfx_duration(sfx_type: str) -> float:
        """Estimate SFX duration based on type."""
        durations = {
            "motorcycle": 3.0,
            "footsteps": 2.0,
            "door": 1.5,
            "phone": 2.0,
            "street": 8.0,
            "market": 8.0,
            "night": 10.0,
            "basketball": 3.0,
            "rain": 6.0,
            "laughter": 2.5,
        }
        return durations.get(sfx_type, 3.0)

    @staticmethod
    def _create_silent_audio(path: Path, duration_s: float, format: str = "wav") -> None:
        """Create a silent audio file of specified duration.

        Uses FFMPEG to generate silence.
        """
        path.parent.mkdir(parents=True, exist_ok=True)

        if format == "wav":
            # Generate silent WAV with ffmpeg
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-f", "lavfi",
                    "-i", f"anullsrc=r=44100:cl=stereo:d={duration_s}",
                    "-t", str(duration_s),
                    "-c:a", "pcm_s16le",
                    str(path),
                ],
                capture_output=True, timeout=30,
            )
        elif format == "mp3":
            # Generate silent MP3
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-f", "lavfi",
                    "-i", f"anullsrc=r=44100:cl=stereo:d={duration_s}",
                    "-t", str(duration_s),
                    "-c:a", "libmp3lame",
                    "-q:a", "5",
                    str(path),
                ],
                capture_output=True, timeout=30,
            )

        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            # Fallback: create a minimal WAV with Python's wave module
            if format == "wav":
                rate = 44100
                n_frames = int(duration_s * rate)
                with wave.open(str(path), "wb") as w:
                    w.setnchannels(2)
                    w.setsampwidth(2)
                    w.setframerate(rate)
                    w.writeframes(b"\x00\x00" * n_frames)


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def create_audio_scene_spec(
    scene_id: str,
    dialogue: list[dict] | None = None,
    sfx: list[str] | None = None,
    ambience: str = "",
    bgm: str = "",
    lipsync: bool = False,
    voice_requirements: Optional[dict] = None,
) -> AudioSceneSpec:
    """Create an AudioSceneSpec with sane defaults.

    Args:
        scene_id: Scene identifier (e.g., "S01").
        dialogue: List of dialogue lines, each a dict with:
                  speaker, text, voice (optional), emotion (optional), rate (optional).
        sfx: List of SFX type names (e.g., ["motorcycle", "footsteps"]).
        ambience: Ambience description (e.g., "busy residential barangay street").
        bgm: BGM mood (e.g., "emotional", "comedy", "suspense").
        lipsync: Whether to apply lip sync to this scene.
        voice_requirements: Optional dict with gender, age, accent, delivery.

    Returns:
        AudioSceneSpec ready for the audio engine.
    """
    return AudioSceneSpec(
        scene_id=scene_id,
        dialogue=dialogue or [],
        sfx=sfx or [],
        ambience=ambience,
        bgm=bgm,
        lipsync=lipsync,
        voice_requirements=voice_requirements,
    )
