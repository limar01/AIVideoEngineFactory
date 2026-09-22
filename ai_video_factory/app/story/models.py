"""Story Engine data models (Pydantic v2).

Defines the artifact shapes produced by the ``StoryEngine`` adapter layer and
consumed by ``app/scenes`` → ``app/prompts``.  The contract is fixed by
``docs/DB_SCHEMA.md`` §3.8 (``stories`` table) and ``ARCHITECTURE.md`` §5.1.

Design notes
------------
* Every field has a default or is required, so templates / stubs can construct
  valid artifacts without an LLM round-trip.
* Models are *not* tied to SQLAlchemy — they are pure Pydantic and serialized
  to JSON in the project artifact folder (ADR-0002 §5.1, persistence rule).
* ``Scene`` mirrors ``DB_SCHEMA.md`` §3.2 so the ScenePlanner can hydrate rows
  directly from a ``StoryDoc``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, ConfigDict

# ---------------------------------------------------------------------------
# Scene-level models (nested inside StoryDoc)
# ---------------------------------------------------------------------------


class Scene(BaseModel):
    """A single video scene within an act.

    Fields map 1:1 to ``DB_SCHEMA.md`` §3.2 ``scene`` table columns so the
    ScenePlanner can lift scenes directly into DB rows.
    """

    scene_number: int = Field(ge=1, description="1-based scene index within the story")
    act_number: int | None = Field(
        default=None, ge=1, description="Act this scene belongs to (nullable if no act structure)"
    )
    title: str = Field(min_length=1, description="Short title / slug for the scene")
    description: str = Field(min_length=1, description="What happens in this scene")
    narration_text: str | None = Field(default=None, description="Voice-over text for the scene")
    narration_seconds: float | None = Field(
        default=None, ge=0, description="Derived duration of narration (seconds)"
    )
    target_clip_seconds: float = Field(default=8.0, gt=0, description="Target clip length (spec §1: 8s)")

    model_config = {"extra": "forbid"}


class Act(BaseModel):
    """A narrative act containing an ordered list of scenes."""

    act_number: int = Field(ge=1, description="1-based act index")
    title: str = Field(min_length=1, description="Act title")
    summary: str | None = Field(default=None, description="One-line summary of the act")
    scenes: list[Scene] = Field(default_factory=list, min_length=1)

    model_config = {"extra": "forbid"}


# ---------------------------------------------------------------------------
# StoryDoc
# ---------------------------------------------------------------------------


class StoryDoc(BaseModel):
    """The complete story artifact: acts, scenes, narration.

    Produced by :meth:`StoryEngine.generate_story`.
    """

    topic: str = Field(min_length=1, description="User-supplied topic (e.g. 'haunted doll')")
    niche: str = Field(min_length=1, description="Niche key matching a config template")
    target_seconds: int = Field(ge=1, description="User target video length in seconds")
    title: str = Field(min_length=1, description="Story title")
    logline: str = Field(min_length=1, description="One-sentence hook")
    acts: list[Act] = Field(min_length=1)

    # --- derived properties ------------------------------------------------

    @property
    def total_scenes(self) -> int:
        """Total number of scenes across all acts."""
        return sum(len(act.scenes) for act in self.acts)

    @property
    def all_scenes(self) -> list[Scene]:
        """Flat, ordered list of every scene in the story."""
        return [scene for act in self.acts for scene in act.scenes]

    def renumber_scenes(self) -> None:
        """Ensure scene_number is 1-based across the whole story."""
        for i, scene in enumerate(self.all_scenes, start=1):
            scene.scene_number = i

    model_config = {"extra": "forbid"}


# ---------------------------------------------------------------------------
# Character Bible
# ---------------------------------------------------------------------------


class Character(BaseModel):
    """A single character in the story."""

    name: str = Field(min_length=1)
    appearance: str = Field(min_length=1, description="Physical description")
    clothing: str = Field(min_length=1, description="Typical outfit / costume")
    props: list[str] = Field(default_factory=list, description="Key props the character carries or interacts with")

    model_config = {"extra": "forbid"}


class CharacterBible(BaseModel):
    """The character bible: list of characters + optional notes.

    Produced by :meth:`StoryEngine.generate_character_bible`.
    """

    characters: list[Character] = Field(default_factory=list)
    notes: str | None = Field(default=None, description="Global casting / character notes")

    model_config = {"extra": "forbid"}


# ---------------------------------------------------------------------------
# Visual Bible
# ---------------------------------------------------------------------------


class VisualBible(BaseModel):
    """The visual bible: style, color, lighting, camera guidance.

    Produced by :meth:`StoryEngine.generate_visual_bible`.
    """

    color_palette: list[str] = Field(default_factory=list, description="Named colors / color families")
    lighting: str = Field(min_length=1, description="Lighting style description")
    camera_style: str = Field(min_length=1, description="Camera movement / framing style")
    notes: str | None = Field(default=None, description="Additional visual direction")
    aspect_ratio: str | None = Field(default=None, description="Recommended aspect ratio, e.g. '16:9'")

    model_config = {"extra": "forbid"}
