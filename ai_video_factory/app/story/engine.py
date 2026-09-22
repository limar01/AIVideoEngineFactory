"""Story Engine adapter layer.

Defines the ``StoryEngine`` ABC (the single seam in ``DEPENDENCY_GRAPH.md`` §3.1)
and the default ``HermesStoryEngine`` that delegates content generation to a
Hermes Desktop subagent.

Swap strategy (ADR-0002): the concrete engine is selected by
``config/story.yaml::engine``.  ``get_story_engine`` is the factory that reads
that config and returns the matching adapter — all downstream modules
(``app/scenes``, ``app/prompts``) depend only on the ``StoryEngine`` interface,
never on a concrete class.

The actual Hermes subagent call is **stubbed** in this foundation step.  The
stub returns minimal-but-valid artifacts derived from the loaded niche template
so the pipeline is end-to-end runnable without any LLM key (free-tier mandate).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import yaml

from app.story.models import Act, Character, CharacterBible, Scene, StoryDoc, VisualBible

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Adapter interface (the seam)
# ---------------------------------------------------------------------------


class StoryEngine(ABC):
    """Abstract story engine — produces StoryDoc, CharacterBible, VisualBible.

    Concrete implementations:
    * ``HermesStoryEngine`` — default; delegates to a Hermes subagent (stubbed).
    * ``OpenAIStoryEngine`` / ``GeminiStoryEngine`` — real LLM (future).

    Every method returns a Pydantic artifact that is serialized to the project's
    artifact folder and linked to a ``Prompt`` row (persistence per spec §11 /
    ARCHITECTURE.md §5.1).
    """

    @abstractmethod
    def generate_story(self, topic: str, niche: str, target_seconds: int) -> StoryDoc:
        """Produce a fully-structured story (acts + scenes + narration)."""

    @abstractmethod
    def generate_character_bible(self, story: StoryDoc) -> CharacterBible:
        """Produce the character bible (appearance / clothing / props)."""

    @abstractmethod
    def generate_visual_bible(self, story: StoryDoc, character_bible: CharacterBible) -> VisualBible:
        """Produce the visual bible (color palette / lighting / camera style)."""


# ---------------------------------------------------------------------------
# Default adapter — Hermes subagent (stubbed for foundation)
# ---------------------------------------------------------------------------


class HermesStoryEngine(StoryEngine):
    """Default free-tier story engine.

    Loads a niche template from ``config/templates/`` and returns minimal
    artifacts so the pipeline works end-to-end without an LLM call.

    In the real implementation each ``generate_*`` method will:
    1. Build a subagent task description from the template + inputs.
    2. Invoke ``hermes.subagent.run(...)`` (Hermes Desktop MCP).
    3. Parse the returned structured JSON into the corresponding Pydantic model.

    Until the subagent integration lands, the methods below return template-
    driven placeholder artifacts.
    """

    DEFAULT_TEMPLATE_DIR = "config/templates"
    DEFAULT_MODEL = "poolside/laguna-s-2.1:free"

    def __init__(
        self,
        template_dir: str | Path = DEFAULT_TEMPLATE_DIR,
        model: str = DEFAULT_MODEL,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.template_dir = Path(template_dir)
        self.model = model
        self._template_cache: dict[str, dict[str, Any]] = {}
        self._hermes_config: dict[str, Any] = (
            config if config is not None else self._load_story_yaml()
        )

    # -- config / template helpers -------------------------------------------

    @staticmethod
    def _load_story_yaml(path: str | Path = "config/story.yaml") -> dict[str, Any]:
        """Load the ``hermes`` block from ``config/story.yaml`` (empty if missing)."""
        story_yaml = Path(path)
        if not story_yaml.exists():
            return {}
        with open(story_yaml) as f:
            data = yaml.safe_load(f) or {}
        return data.get("hermes", {})

    def load_template(self, niche: str) -> dict[str, Any]:
        """Load and cache a niche template YAML file."""
        if niche in self._template_cache:
            return self._template_cache[niche]
        template_path = self.template_dir / f"{niche}.yaml"
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found for niche '{niche}': {template_path}")
        with open(template_path) as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise TypeError(f"Template {template_path} did not parse to a dict")
        self._template_cache[niche] = data
        return data

    def _model_preferences(self, niche: str) -> str:
        """Return the model preference for *niche* (reads story.yaml config)."""
        prefs: dict[str, Any] = self._hermes_config.get("model_preferences", {})
        return str(prefs.get(niche, prefs.get("default", self.DEFAULT_MODEL)))

    # -- stub implementations -----------------------------------------------

    def generate_story(self, topic: str, niche: str, target_seconds: int) -> StoryDoc:
        """STUB: generate_story would invoke a Hermes subagent.

        Returns a minimal single-act StoryDoc derived from the niche template
        so downstream scenes/prompts have valid data to consume.
        """
        template = self.load_template(niche)
        logger.info(
            "HermesStoryEngine.generate_story [STUB] — "
            "subagent call not yet implemented (topic=%r, niche=%r, target=%ds, model=%s)",
            topic,
            niche,
            target_seconds,
            self._model_preferences(niche),
        )

        pacing = str(template.get("story_structure", {}).get("pacing", "moderate"))

        act = Act(
            act_number=1,
            title="Act I",
            summary=f"A {niche} story about {topic}.",
            scenes=[
                Scene(
                    scene_number=1,
                    act_number=1,
                    title="Opening",
                    description=f"Sets up the premise: a {topic} in a {pacing} atmosphere.",
                    narration_text=f"In a {pacing} tale of {niche}, something stirs around {topic}.",
                    target_clip_seconds=8.0,
                    narration_seconds=5.0,
                ),
                Scene(
                    scene_number=2,
                    act_number=1,
                    title="Tension Rises",
                    description="The tension curve peaks as the threat reveals itself.",
                    narration_text="The air grows cooler. Something is watching.",
                    target_clip_seconds=8.0,
                    narration_seconds=4.0,
                ),
            ],
        )

        return StoryDoc(
            topic=topic,
            niche=niche,
            target_seconds=target_seconds,
            title=f"The {topic.replace('_', ' ').title()}",
            logline=f"A {niche} story where {topic} awakens a darkness.",
            acts=[act],
        )

    def generate_character_bible(self, story: StoryDoc) -> CharacterBible:
        """STUB: generate_character_bible would invoke a Hermes subagent."""
        template = self.load_template(story.niche)
        logger.info(
            "HermesStoryEngine.generate_character_bible [STUB] — "
            "subagent call not yet implemented (topic=%r)",
            story.topic,
        )
        mood = str(template.get("visual_guidance", {}).get("mood", "unsettling"))
        return CharacterBible(
            characters=[
                Character(
                    name="The Protagonist",
                    appearance="Unseen silhouette, ordinary clothing, cautious demeanor.",
                    clothing="Casual dark clothing suitable for nighttime",
                    props=["Flashlight", "Phone (dead battery)"],
                )
            ],
            notes=f"Visual style: {mood}.",
        )

    def generate_visual_bible(self, story: StoryDoc, character_bible: CharacterBible) -> VisualBible:
        """STUB: generate_visual_bible would invoke a Hermes subagent."""
        template = self.load_template(story.niche)
        vg: dict[str, Any] = template.get("visual_guidance", {})
        logger.info(
            "HermesStoryEngine.generate_visual_bible [STUB] — "
            "subagent call not yet implemented (topic=%r)",
            story.topic,
        )
        return VisualBible(
            color_palette=list(vg.get("color_palette", ["black", "deep_red"])),
            lighting=str(vg.get("lighting", "low_contrast")),
            camera_style=str(vg.get("camera_style", "tight_closeups")),
            notes=str(vg.get("mood")) if vg.get("mood") else None,
            aspect_ratio=str(vg.get("recommended_aspect_ratio")) if vg.get("recommended_aspect_ratio") else None,
        )


# ---------------------------------------------------------------------------
# Factory / registry (the seam — config-driven engine selection)
# ---------------------------------------------------------------------------

_ENGINE_REGISTRY: dict[str, type[StoryEngine]] = {
    "hermes": HermesStoryEngine,
}


def register_engine(name: str, cls: type[StoryEngine]) -> None:
    """Register a new StoryEngine implementation (e.g. OpenAIStoryEngine)."""
    _ENGINE_REGISTRY[name] = cls


def get_story_engine(
    engine_name: str | None = None,
    config_path: str | Path = "config/story.yaml",
) -> StoryEngine:
    """Factory: return the configured StoryEngine instance.

    Reads ``config/story.yaml::engine`` (default ``"hermes"``) and instantiates
    the matching registered class.  This is the single seam documented in
    DEPENDENCY_GRAPH.md §3.1 — downstream code calls this factory, never the
    concrete class directly.
    """
    resolved: str
    if engine_name is None:
        cfg_path = Path(config_path)
        if cfg_path.exists():
            with open(cfg_path) as f:
                data = yaml.safe_load(f) or {}
            resolved = str(data.get("engine", "hermes"))
        else:
            resolved = "hermes"
    else:
        resolved = engine_name

    cls = _ENGINE_REGISTRY.get(resolved)
    if cls is None:
        raise ValueError(
            f"Unknown story engine '{resolved}'. "
            f"Registered: {sorted(_ENGINE_REGISTRY)}"
        )
    return cls()
