"""Prompts module - scene-to-prompt compiler for SnapGen/Veo.

Format: cinematic continuous shot with character outfit/props/background locked,
Taglish dialogue in prompt (Veo generates audio), negative prompts for consistency.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.scenes.planner import PlanarScene

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider Prompt Adapter base
# ---------------------------------------------------------------------------


class PromptAdapter:
    """Base prompt adapter."""
    def format_prompt(
        self,
        scene: PlanarScene,
        continuity_dna: dict[str, Any] | None = None,
    ) -> str:
        raise NotImplementedError

    def get_negative_prompt(self, scene: PlanarScene) -> str:
        return ""


# ---------------------------------------------------------------------------
# SnapGen/Veo Prompt Adapter - Pinoy drama format
# ---------------------------------------------------------------------------


class SnapGenPromptAdapter(PromptAdapter):
    """Format scenes for SnapGen Veo 3.1.

    Veo generates video WITH audio from prompt text. Taglish dialogue and
    narration baked in as text. Character consistency via continuity DNA
    (outfit/props/background per scene). Genre tone injected from visual bible
    or continuity DNA.
    """

    ASPECT_RATIO = "9:16"
    RESOLUTION = "1080p"
    DURATION = "8s"

    _GENRE_TONE: dict[str, str] = {
        "horror": (
            "Haunted house atmosphere: dusty wooden floor creaking, peeling "
            "wallpaper, shadows in corners, flickering bulb, cold air, "
            "oppressive and claustrophobic mood, low contrast with sporadic "
            "highlights, dark tones."
        ),
        "pinoy_drama": (
            "Warm Filipino family atmosphere: soft afternoon light through "
            "window, ceiling fan turning slowly, family photos on wall, "
            "simple wooden furniture, warm golden hour lighting."
        ),
        "default": (
            "Cinematic setting with natural lighting, detailed environment."
        ),
    }

    def format_prompt(
        self,
        scene: PlanarScene,
        continuity_dna: dict[str, Any] | None = None,
    ) -> str:
        cd = continuity_dna or {}

        char_block = self._character_block(scene, cd)
        bg_block = self._background_block(scene, cd)
        action_block = self._action_block(scene)
        dialogue_block = self._dialogue_block(scene, cd)
        sfx_block = self._sfx_block()

        prompt = (
            f"Cinematic continuous shot, {self.ASPECT_RATIO} vertical video.\n"
            f"Resolution: {self.RESOLUTION}.\n"
            f"{bg_block}\n"
            f"{char_block}\n"
            f"{action_block}\n"
            f"{dialogue_block}\n"
            f"{sfx_block}\n"
            f"Natural lighting, continuous camera, smooth cinematic shot."
        )
        return prompt

    def _genre_tone(self, scene: PlanarScene, cd: dict[str, Any]) -> str:
        """Determine genre tone from scene, continuity DNA, or visual bible cues."""
        # Check continuity DNA for explicit genre
        genre = cd.get("genre")
        if genre and genre in self._GENRE_TONE:
            return self._GENRE_TONE[genre]

        # Check scene description/narration for horror cues
        desc = getattr(scene, "description", "") or ""
        narration = getattr(scene, "narration_text", "") or ""
        combined = f"{desc} {narration}".lower()
        horror_keywords = ["horror", "dark", "scary", "oppressive", "claustrophobic",
                           "haunted", "fear", "dread", "shadow", "cold", "tense"]
        if any(kw in combined for kw in horror_keywords):
            return self._GENRE_TONE["horror"]

        # Default to Pinoy drama warm tone
        return self._GENRE_TONE["pinoy_drama"]

    def _character_block(
        self, scene: PlanarScene, cd: dict[str, Any],
    ) -> str:
        chars = getattr(scene, "characters", cd.get("characters", []))
        outfits = cd.get("outfits", {})

        # Character descriptions with locked outfit/props per character
        char_descs: dict[str, str] = {
            "Aling Nena": (
                "Aling Nena: matang woman with warm face and natural makeup, "
                "wearing white work blouse with floral print and dark blue skirt, "
                "simple gold necklace, hair in neat bun with loose strands, "
                "holding oblong plastic bag with market goods, "
                "hand on hip with concerned expression"
            ),
            "Kiko": (
                "Kiko: lanky young man with tired eyes and stubble on chin, "
                "wearing faded black band t-shirt slightly oversized and grey joggers, "
                "scuffed canvas shoes, silver ring on right hand, "
                "holding cellphone with cracked screen, "
                "arms crossed avoiding eye contact"
            ),
            "Mia": (
                "Mia: petite girl with long dark hair in ponytail and bright observant eyes, "
                "wearing white school blouse with grey pleated skirt, "
                "black ribbon in hair, simple stud earrings, "
                "holding small notebook and pencil case, "
                "head tilted with finger on chin when thinking"
            ),
            "Apo Lola": (
                "Apo Lola: elderly woman with kind wrinkled face and silver hair in braid, "
                "wearing traditional Filipino terno dress in subdued colors with "
                "knit shawl over shoulders and simple earrings, "
                "holding rosary beads, seated calmly with gentle smile"
            ),
        }

        # Handle list-of-dicts format from continuity DNA
        if chars and isinstance(chars[0], dict):
            parts = []
            for c in chars:
                name = c.get("name", "")
                if name and name in char_descs:
                    parts.append(char_descs[name])
                elif name:
                    clothing = c.get("clothing", "")
                    props = c.get("props", [])
                    parts.append(
                        f"{name}: {clothing}, carrying: {', '.join(props) if props else 'nothing'}"
                    )
            if parts:
                return "Characters: " + " | ".join(parts) + " |"
            return "Characters present."

        # String list format
        parts = []
        for name in chars:
            desc = char_descs.get(name)
            if desc:
                parts.append(desc)
        if parts:
            return "Characters: " + " | ".join(parts) + " |"
        return "Characters present."

    def _background_block(
        self, scene: PlanarScene, cd: dict[str, Any],
    ) -> str:
        bg = getattr(scene, "background_scene", cd.get("background", ""))
        tone = self._genre_tone(scene, cd)

        if not bg:
            return f"Setting: {tone}."

        return f"Setting: {bg}. {tone}"

    def _action_block(self, scene: PlanarScene) -> str:
        narration = getattr(scene, "narration_text", "") or ""
        if narration:
            clean = narration.replace(
                "[VOICEOVER]:", ""
            ).replace("[DIALOGUE]:", "").strip()
            return f"Action: {clean}"
        return "Action: The characters interact naturally in the scene."

    def _dialogue_block(
        self, scene: PlanarScene, cd: dict[str, Any],
    ) -> str:
        dialogue = getattr(scene, "dialogue_lines", cd.get("dialogue", []))
        if not dialogue:
            return "Dialogue: Natural Taglish conversation between characters."

        lines = []
        for speaker, text in dialogue:
            lines.append(f"{speaker}: \"{text}\"")
        return "Taglish dialogue (Tagalog-English): " + " ".join(lines) + "."

    def _sfx_block(self) -> str:
        return (
            "Audio: natural ambient sounds - ceiling fan, distant street traffic, "
            "soft Filipino family conversation background, emotional piano BGM, "
            "subtle SFX matching action. Clear dialogue audio."
        )

    def get_negative_prompt(self, scene: PlanarScene) -> str:
        return (
            "--no: cartoon, anime, 3d render, cgi, morphing faces, "
            "inconsistent clothing, extra limbs, deformed hands, "
            "blurry face, low resolution, text overlays, watermark, "
            "disconnected audio, out of sync, bad lip sync, "
            "studio lighting, neon colors, cyberpunk, futuristic"
        )


# ---------------------------------------------------------------------------
# CompiledPrompt
# ---------------------------------------------------------------------------


@dataclass
class CompiledPrompt:
    scene_id: str
    scene_number: int
    provider: str
    prompt_text: str
    version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    @property
    def text(self) -> str:
        return self.prompt_text

    @property
    def act_number(self) -> int | None:
        return self.metadata.get("act_number")

    @property
    def adapter(self) -> str:
        return self.provider

    @property
    def clip_seconds(self) -> float:
        return float(self.metadata.get("target_clip_seconds") or 0.0)


# ---------------------------------------------------------------------------
# PromptCompiler
# ---------------------------------------------------------------------------


class PromptCompiler:
    """Compile scenes into provider-ready prompts with continuity DNA injection."""

    def __init__(
        self,
        provider: str = "snapgen",
        adapter: PromptAdapter | None = None,
    ) -> None:
        self.provider = provider
        self.adapter = adapter or SnapGenPromptAdapter()
        logger.info("PromptCompiler initialized (provider=%s)", provider)

    def compile(
        self,
        scene: PlanarScene | list[PlanarScene],
        *,
        story: Any = None,
        character_bible: Any = None,
        visual_bible: Any = None,
        **kwargs: Any,
    ) -> CompiledPrompt | list[CompiledPrompt]:
        if isinstance(scene, list):
            return self.compile_multi(
                scene,
                story=story,
                character_bible=character_bible,
                visual_bible=visual_bible,
                **kwargs,
            )
        return self._compile_one(scene)

    def _compile_one(self, scene: PlanarScene) -> CompiledPrompt:
        try:
            continuity = json.loads(scene.continuity_dna) if scene.continuity_dna else {}
        except (json.JSONDecodeError, TypeError):
            continuity = {}

        prompt_text = self.adapter.format_prompt(scene, continuity)
        negative = self.adapter.get_negative_prompt(scene)

        cp = CompiledPrompt(
            scene_id=getattr(scene, "scene_id", None) or str(scene.scene_number),
            scene_number=scene.scene_number,
            provider=self.provider,
            prompt_text=prompt_text,
            version=1,
            metadata={
                "complexity": getattr(scene, "complexity", "LOW"),
                "narration_seconds": getattr(scene, "narration_seconds", 8.0),
                "target_clip_seconds": getattr(scene, "target_clip_seconds", 8.0),
                "continuity_dna": scene.continuity_dna,
                "act_number": getattr(scene, "act_number", None),
                "negative_prompt": negative,
            },
            created_at="",
        )
        # Attach prompt to the scene so downstream (assembly/QA) can access it
        try:
            scene.prompts = [{"text": prompt_text, "provider": self.provider, "version": 1}]
        except (AttributeError, ValueError):
            pass  # scene model without a prompts field (e.g. story Scene)
        return cp

    def compile_multi(
        self,
        scenes: list[PlanarScene],
        *,
        story: Any = None,
        character_bible: Any = None,
        visual_bible: Any = None,
        **kwargs: Any,
    ) -> list[CompiledPrompt]:
        results: list[CompiledPrompt] = []
        for scene in scenes:
            cd = self._build_continuity_dna(
                scene, story, character_bible, visual_bible
            )
            scene.continuity_dna = json.dumps(cd)
            results.append(self._compile_one(scene))
        return results

    def _build_continuity_dna(
        self,
        scene: PlanarScene,
        story: Any = None,
        character_bible: Any = None,
        visual_bible: Any = None,
    ) -> dict[str, Any]:
        cd: dict[str, Any] = {
            "characters": getattr(scene, "characters", []) or [],
            "background": getattr(scene, "background_scene", None),
            "outfits": {},
            "dialogue": getattr(scene, "dialogue_lines", []) or [],
            "aspect_ratio": "9:16",
            "camera_style": "continuous cinematic shot vertical",
        }

        for name in cd["characters"]:
            outfit = getattr(scene, "outfit_description", "") or ""
            if outfit:
                cd["outfits"][name] = outfit

        # Carry genre from visual bible or story niche
        if visual_bible is not None:
            cd["aspect_ratio"] = getattr(visual_bible, "aspect_ratio", "9:16")
            cd["camera_style"] = getattr(visual_bible, "camera_style", "")
            mood = getattr(visual_bible, "mood", "") or ""
            if mood:
                cd["genre"] = "horror" if any(kw in mood.lower() for kw in ["oppressive", "claustrophobic", "dark", "tense"]) else "pinoy_drama"

        if story is not None:
            niche = getattr(story, "niche", "") or ""
            if niche and "genre" not in cd:
                cd["genre"] = "horror" if niche == "horror" else "pinoy_drama"

        return cd

    def repair(
        self,
        prompt: CompiledPrompt,
        failure_reason: str,
    ) -> CompiledPrompt:
        return prompt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _optimize_description(description: str, complexity: str) -> str:
    text = description.strip()
    text = re.sub(
        r"\b(simultaneously|while|meanwhile|at the same time)\b",
        " and then ",
        text,
        flags=re.IGNORECASE,
    )
    if complexity == "HIGH":
        text = f"Focus on one clear action: {text}"
    return text.strip()[:200]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


_ADAPTERS: dict[str, type[PromptAdapter]] = {
    "snapgen": SnapGenPromptAdapter,
}


def get_prompt_adapter(provider: str) -> PromptAdapter:
    cls = _ADAPTERS.get(provider, SnapGenPromptAdapter)
    return cls()