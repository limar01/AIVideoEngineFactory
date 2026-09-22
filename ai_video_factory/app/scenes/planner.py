"""Scenes module — story-to-scenes compiler.

Source: docs/ARCHITECTURE.md §4.4 (app/scenes/)
        docs/DEPENDENCY_GRAPH.md §3.3 (Scene Planner)
        Master Spec §1 (8-second clips), §7 (scene optimization), §23 (narration style)

Transforms a StoryDoc + CharacterBible + VisualBible into a list of PlanarScenes.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.story.models import StoryDoc, Scene as StoryScene, CharacterBible, VisualBible

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Data classes
# --------------------------------------------------------------------------- #


@dataclass
class PlanarScene:
    """A scene plan — output of ScenePlanner, input to PromptCompiler.

    Mirrors DB schema §3.2 ``scene`` table columns.
    """
    scene_id: str
    scene_number: int
    act_number: int | None
    title: str
    description: str
    narration_text: str | None
    narration_seconds: float | None  # DERIVED from narration text, not duration
    target_clip_seconds: float       # target clip duration for the provider
    complexity: str                  # LOW | MEDIUM | HIGH
    continuity_dna: str             # JSON string of visual + character anchors
    narration: dict[str, Any]       # narration metadata: text, seconds, hook, style
    prompts: list[dict[str, Any]] = field(default_factory=list)

    @property
    def prompt(self) -> str:
        """Compiled provider prompt (spec §6 scene field), attached by the
        PromptCompiler after compilation; empty before that."""
        if self.prompts:
            first = self.prompts[0]
            return first.get("text", "") or first.get("prompt_text", "")
        return ""

    @property
    def clip_seconds(self) -> float:
        """Integration-harness contract alias for ``target_clip_seconds``.

        Additive alias (2026-09-22 provider-contract fix): e2e tests and the
        Master Spec tooling read ``clip_seconds``; the canonical field name
        ``target_clip_seconds`` is unchanged.
        """
        return self.target_clip_seconds


# --------------------------------------------------------------------------- #
# ScenePlanner
# --------------------------------------------------------------------------- #


class ScenePlanner:
    """Transforms a StoryDoc + bibles into a list of PlanarScenes.

    Key design decision (ADR-0001 / spec §10 gap):
    Scene count is derived from **narration timing**, not target_seconds / 8.
    A 10-minute (600s) horror story with 300s of narration at 8s clips needs
    ~38 clips, not 75.  The narrator's pacing drives scene count.
    """

    def __init__(
        self,
        target_clip_seconds: float = 8.0,
        narration_pace_words_per_minute: int = 150,
        min_narration_seconds: float = 2.0,
    ):
        self.target_clip_seconds = target_clip_seconds
        self._narration_pace_words_per_minute = narration_pace_words_per_minute
        self.words_per_second = narration_pace_words_per_minute / 60.0
        self.min_narration_seconds = min_narration_seconds
        logger.info(
            "ScenePlanner initialized: clip=%ss, pace=%swpm, min_narration=%ss",
            target_clip_seconds, narration_pace_words_per_minute, min_narration_seconds,
        )

    def compute_narration_seconds(self, narration_text: str | None) -> float | None:
        """Derive narration duration from text word count.

        Uses a rough reading pace: ~150 words per minute = 2.5 words/second.
        Returns None for empty/None text.
        """
        if not narration_text or not narration_text.strip():
            return None
        words = len(narration_text.split())
        seconds = max(self.min_narration_seconds, words / self.words_per_second)
        return round(seconds, 2)

    def classify_complexity(self, scene: StoryScene) -> str:
        """Classify scene complexity for provider prompt optimization.

        LOW: single action, single subject, simple setting
        MEDIUM: multiple elements, some action sequence
        HIGH: multiple characters, conflicting/simultaneous actions
        """
        desc = scene.description.lower()
        score = 0

        # Multiple distinct characters mentioned
        character_indicators = ["character", "man", "woman", "child", "figure", "person"]
        char_count = sum(1 for w in character_indicators if w in desc)
        if char_count > 1:
            score += 2

        # Multiple action verbs
        action_verbs = ["runs", "walks", "turns", "looks", "grabs", "opens",
                         "closes", "holds", "reaches", "steps", "falls", "flees",
                         "rises", "descends", "appears", "disappears"]
        action_count = sum(1 for v in action_verbs if v in desc)
        if action_count >= 2:
            score += 1

        # Conflicting/simultaneous actions (hard for AI video generators)
        conflict_words = ["while", "meanwhile", "simultaneously", "as",
                          "at the same time", "during", "and in the background"]
        if any(w in desc for w in conflict_words):
            score += 2

        if score >= 3:
            return "HIGH"
        elif score >= 1:
            return "MEDIUM"
        else:
            return "LOW"

    def build_continuity_dna(
        self,
        scene: StoryScene,
        character_bible: CharacterBible,
        visual_bible: VisualBible,
        scene_index: int,
    ) -> str:
        """Build continuity DNA JSON for a scene.

        Captures visual anchors (color palette, lighting, camera, aspect) and
        character anchors (appearance, clothing, props) so the prompt compiler
        can inject consistency tokens into every provider prompt.

        Source: ARCHITECTURE.md §5.6, DEPENDENCY_GRAPH.md §4.1
        """
        dna: dict[str, Any] = {
            "scene_index": scene_index,
            "characters": [],
            "visual_anchors": {
                "color_palette": visual_bible.color_palette or [],
                "lighting": visual_bible.lighting or "natural",
                "camera_style": visual_bible.camera_style or "static",
                "aspect_ratio": visual_bible.aspect_ratio or "16:9",
            },
        }

        for char in character_bible.characters:
            dna["characters"].append({
                "name": char.name,
                "appearance": char.appearance,
                "clothing": char.clothing,
                "props": list(char.props),
            })

        return json.dumps(dna, indent=2)

    def plan(
        self,
        story: StoryDoc,
        character_bible: CharacterBible,
        visual_bible: VisualBible,
        *,
        target_clip_seconds: float | None = None,
    ) -> list[PlanarScene]:
        """Plan all scenes from a StoryDoc.

        Steps:
        1. Compute narration_seconds for each scene
        2. Classify complexity
        3. Build continuity DNA
        4. Assemble PlanarScene list

        Returns scenes sorted by scene_number.
        """
        tcs = target_clip_seconds if target_clip_seconds is not None else self.target_clip_seconds
        scenes: list[PlanarScene] = []

        for idx, story_scene in enumerate(story.all_scenes, start=1):
            narration_seconds = self.compute_narration_seconds(story_scene.narration_text)

            dna = self.build_continuity_dna(
                story_scene, character_bible, visual_bible, idx - 1,
            )

            planar = PlanarScene(
                scene_id=f"scene-{idx:03d}",
                scene_number=idx,
                act_number=story_scene.act_number,
                title=story_scene.title,
                description=story_scene.description,
                narration_text=story_scene.narration_text,
                narration_seconds=narration_seconds,
                target_clip_seconds=tcs,
                complexity=self.classify_complexity(story_scene),
                continuity_dna=dna,
                narration={
                    "text": story_scene.narration_text,
                    "seconds": narration_seconds,
                    "style": "standard",
                },
                prompts=[],
            )
            scenes.append(planar)

        total_narration = sum(
            s.narration_seconds or 0 for s in scenes
        )
        estimated_clips = max(1, round(total_narration / self.target_clip_seconds))

        logger.info(
            "ScenePlanner.plan: %d scenes planned, total narration=%ss → ~%d clips for '%s' (%s)",
            len(scenes), round(total_narration, 1), estimated_clips,
            story.title, story.niche,
        )
        return scenes
