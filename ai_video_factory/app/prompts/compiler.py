"""Prompts module — scene-to-prompt compiler.

Source: docs/ARCHITECTURE.md §4.5 (app/prompts/)
        docs/PROVIDER_INTERFACE.md §5.4 (prompt formatting)
        Master Spec §8 (compile provider-ready prompts), §19 (scene optimization),
        §23 (narration style templates)

Responsible for:
- Converting PlanarScenes into provider-ready prompt strings
- Provider adapter pattern (SnapGen/Veo, Grok, etc. — different prompt formats)
- Prompt versioning (v1, v2...) for repair integration
- Injecting continuity DNA tokens into prompts
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.scenes.planner import PlanarScene
from app.story.models import StoryDoc, CharacterBible, VisualBible

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Provider Prompt Adapter (ABC for provider-specific formatting)
# --------------------------------------------------------------------------- #


class PromptAdapter:
    """Transform a PlanarScene into a provider-ready prompt string.

    Subclasses override ``format_prompt`` to produce provider-specific output.
    The default SnapGen/Veo adapter is provided below.
    """

    def format_prompt(self, scene: PlanarScene, continuity_dna: dict[str, Any] | None = None) -> str:
        """Convert a PlanarScene into a single prompt string."""
        raise NotImplementedError

    def inject_continuity(self, prompt: str, continuity_dna: dict[str, Any]) -> str:
        """Inject continuity tokens into an existing prompt."""
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# Default adapter: SnapGen / Google Veo 3.1 style
# --------------------------------------------------------------------------- #


class SnapGenPromptAdapter(PromptAdapter):
    """Default adapter for SnapGen (Google Veo 3.1) prompts.

    Format: concise visual description + scene context + technical settings.
    """

    def __init__(self, aspect_ratio: str = "9:16", resolution: str = "720p"):
        self.aspect_ratio = aspect_ratio
        self.resolution = resolution

    def format_prompt(self, scene: PlanarScene, continuity_dna: dict[str, Any] | None = None) -> str:
        parts: list[str] = []

        # Visual description (single clear action, optimized for AI video)
        visual = _optimize_description(scene.description, self.complexity_weight(scene))
        parts.append(visual)

        # Continuity tokens from character bible
        if continuity_dna and continuity_dna.get("characters"):
            for char in continuity_dna["characters"]:
                parts.append(
                    f"Character: {char['name']} "
                    f"({char['appearance']}, {char['clothing']})"
                )

        # Visual anchors
        anchors = continuity_dna.get("visual_anchors", {}) if continuity_dna else {}
        if anchors.get("color_palette"):
            parts.append(f"Colors: {', '.join(anchors['color_palette'])}")
        if anchors.get("lighting"):
            parts.append(f"Lighting: {anchors['lighting']}")
        if anchors.get("camera_style"):
            parts.append(f"Camera: {anchors['camera_style']}")

        # Technical settings
        parts.append(
            f"Aspect ratio: {self.aspect_ratio}, "
            f"Resolution: {self.resolution}, "
            f"Duration: ~{scene.target_clip_seconds:.1f}s"
        )

        return ". ".join(parts) + "."

    def inject_continuity(self, prompt: str, continuity_dna: dict[str, Any]) -> str:
        """Inject continuity tokens into a prompt string."""
        if not continuity_dna.get("characters"):
            return prompt

        tokens: list[str] = []
        for char in continuity_dna["characters"]:
            tokens.append(f"{char['name']} in {char['clothing']}")

        # Append continuity reminder
        if tokens:
            return prompt + f" [Maintain consistency: {'; '.join(tokens)}]"
        return prompt

    @staticmethod
    def complexity_weight(scene: PlanarScene) -> str:
        """Return the complexity weight for prompt optimization."""
        return scene.complexity


# --------------------------------------------------------------------------- #
# PromptCompiler
# --------------------------------------------------------------------------- #


@dataclass
class CompiledPrompt:
    """A compiled prompt with version and metadata."""
    scene_id: str
    scene_number: int
    provider: str
    prompt_text: str
    version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""  # ISO timestamp


class PromptCompiler:
    """Compile PlanarScenes into provider-ready prompts with versioning.

    Source: docs/ARCHITECTURE.md §5.3, Master Spec §8
    """

    def __init__(
        self,
        provider: str = "snapgen",
        adapter: PromptAdapter | None = None,
    ):
        self.provider = provider
        self.adapter = adapter or SnapGenPromptAdapter()
        logger.info("PromptCompiler initialized (provider=%s)", provider)

    def compile(self, scene: PlanarScene) -> CompiledPrompt:
        """Compile a single scene into a provider-ready prompt."""
        try:
            continuity = json.loads(scene.continuity_dna) if scene.continuity_dna else {}
        except (json.JSONDecodeError, TypeError):
            continuity = {}

        prompt_text = self.adapter.format_prompt(scene, continuity)
        prompt_text = self.adapter.inject_continuity(prompt_text, continuity)

        return CompiledPrompt(
            scene_id=scene.scene_id,
            scene_number=scene.scene_number,
            provider=self.provider,
            prompt_text=prompt_text,
            version=1,
            metadata={
                "complexity": scene.complexity,
                "narration_seconds": scene.narration_seconds,
                "target_clip_seconds": scene.target_clip_seconds,
                "continuity_dna": scene.continuity_dna,
                "act_number": scene.act_number,
            },
            created_at="",
        )

    def compile_multi(
        self,
        scenes: list[PlanarScene],
        *,
        story: StoryDoc | None = None,
        character_bible: CharacterBible | None = None,
        visual_bible: VisualBible | None = None,
        adapters: list[PromptAdapter] | None = None,
        **kwargs: Any,
    ) -> list[CompiledPrompt]:
        """Compile multiple scenes into provider-ready prompts.

        Args:
            scenes: List of PlanarScenes to compile.
            story: Optional StoryDoc (for context metadata).
            character_bible: Optional CharacterBible.
            visual_bible: Optional VisualBible.
            adapters: Optional list of PromptAdapters. Uses the instance adapter if none provided.
            **kwargs: Additional context passed through to adapters.

        Returns:
            List of CompiledPrompt, one per scene.
        """
        adapters = adapters or [self.adapter]
        adapter = adapters[0]  # Use primary adapter

        results: list[CompiledPrompt] = []
        for scene in scenes:
            try:
                continuity = json.loads(scene.continuity_dna) if scene.continuity_dna else {}
            except (json.JSONDecodeError, TypeError):
                continuity = {}

            prompt_text = adapter.format_prompt(scene, continuity)
            prompt_text = adapter.inject_continuity(prompt_text, continuity)

            results.append(CompiledPrompt(
                scene_id=scene.scene_id,
                scene_number=scene.scene_number,
                provider=self.provider,
                prompt_text=prompt_text,
                version=1,
                metadata={
                    "complexity": scene.complexity,
                    "narration_seconds": scene.narration_seconds,
                    "target_clip_seconds": scene.target_clip_seconds,
                    "continuity_dna": scene.continuity_dna,
                    "act_number": scene.act_number,
                    "story_title": story.title if story else None,
                    "niche": story.niche if story else None,
                },
                created_at="",
            ))
        return results

    def compile_all(self, scenes: list[PlanarScene]) -> list[CompiledPrompt]:
        """Compile all scenes into provider-ready prompts."""
        return [self.compile(s) for s in scenes]

    def create_repaired_prompt(
        self,
        old_prompt: CompiledPrompt,
        repaired_description: str,
        new_version: int,
    ) -> CompiledPrompt:
        """Create a repaired prompt (v+1) from a failed generation.

        Called by the repair engine when a scene fails — creates a new prompt
        with a simplified/repaired description while preserving continuity.
        """
        scene_id = old_prompt.scene_id
        continuity_raw = old_prompt.metadata.get("continuity_dna", "{}")
        try:
            continuity = json.loads(continuity_raw) if continuity_raw else {}
        except (json.JSONDecodeError, TypeError):
            continuity = {}

        # Build a new prompt with the repaired description
        # (Simplified version of format_prompt with the new description)
        visual = _optimize_description(repaired_description, "LOW")
        prompt_parts: list[str] = [visual]

        if continuity.get("characters"):
            for char in continuity["characters"]:
                prompt_parts.append(
                    f"Character: {char['name']} "
                    f"({char['appearance']}, {char['clothing']})"
                )

        anchors = continuity.get("visual_anchors", {})
        if anchors.get("color_palette"):
            prompt_parts.append(f"Colors: {', '.join(anchors['color_palette'])}")
        if anchors.get("lighting"):
            prompt_parts.append(f"Lighting: {anchors['lighting']}")

        prompt_text = ". ".join(prompt_parts) + "."

        return CompiledPrompt(
            scene_id=scene_id,
            scene_number=old_prompt.scene_number,
            provider=self.provider,
            prompt_text=prompt_text,
            version=new_version,
            metadata={
                "complexity": "LOW",
                "narration_seconds": old_prompt.metadata.get("narration_seconds"),
                "target_clip_seconds": old_prompt.metadata.get("target_clip_seconds"),
                "continuity_dna": continuity_raw,
                "repair_strategy": "simplify_description",
            },
            created_at="",
        )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _optimize_description(description: str, complexity: str) -> str:
    """Simplify a scene description for AI video generation.

    Free-tier generators struggle with:
    - Multiple simultaneous actions ("A runs while B talks")
    - Complex camera moves
    - Too many characters at once
    """
    import re

    text = description.strip()

    # Replace simultaneous-action connectors with sequential framing
    text = re.sub(
        r'\b(simultaneously|while|meanwhile|at the same time)\b',
        ' and then ',
        text,
        flags=re.IGNORECASE,
    )

    # If HIGH complexity, prepend a "single focus" hint
    if complexity == "HIGH":
        text = f"Focus on one clear action: {text}"

    return text.strip()[:200]  # Keep prompts concise


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #


_ADAPTERS: dict[str, type[PromptAdapter]] = {
    "snapgen": SnapGenPromptAdapter,
}


def get_prompt_adapter(provider: str) -> PromptAdapter:
    """Get a prompt adapter for the given provider."""
    cls = _ADAPTERS.get(provider, SnapGenPromptAdapter)
    return cls()
