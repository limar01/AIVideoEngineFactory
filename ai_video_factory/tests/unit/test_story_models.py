"""Unit tests for story engine data models and HermesStoryEngine stub.

Covers (1) Pydantic model validation & derived properties, (2) the StoryEngine
ABC contract, (3) the HermesStoryEngine stub returning valid template-driven
artifacts, and (4) the config-driven factory seam.

Run:  .venv/bin/pytest tests/unit/test_story_models.py -v
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.story.engine import HermesStoryEngine, StoryEngine, get_story_engine, register_engine
from app.story.models import (
    Act,
    Character,
    CharacterBible,
    Scene,
    StoryDoc,
    VisualBible,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = PROJECT_ROOT / "config" / "templates"


@pytest.fixture
def sample_character() -> Character:
    return Character(
        name="Mara",
        appearance="Pale, hollow eyes, black hair in a loose braid",
        clothing="Tattered nightgown, barefoot",
        props=["Rusted key", "Cracked mirror"],
    )


@pytest.fixture
def sample_character_bible(sample_character: Character) -> CharacterBible:
    return CharacterBible(
        characters=[sample_character],
        notes="All characters have a reflected-counterpart in mirrors.",
    )


@pytest.fixture
def sample_visual_bible() -> VisualBible:
    return VisualBible(
        color_palette=["deep_red", "dark_blue", "black"],
        lighting="low_contrast_with_sporadic_highlights",
        camera_style="tight_closeups_then_wide_reveal",
        notes="Oppressive and claustrophobic",
        aspect_ratio="16:9",
    )


@pytest.fixture
def sample_story_doc() -> StoryDoc:
    return StoryDoc(
        topic="haunted doll",
        niche="horror",
        target_seconds=600,
        title="The Watcher in the Wood",
        logline="A vintage doll awakens something ancient in the forest.",
        acts=[
            Act(
                act_number=1,
                title="The Discovery",
                summary="The protagonist finds a mysterious doll.",
                scenes=[
                    Scene(
                        scene_number=1,
                        act_number=1,
                        title="The Attic",
                        description="Dusty attic, a doll sits upright.",
                        narration_text="She brushed away the cobwebs and froze.",
                        target_clip_seconds=8.0,
                    ),
                    Scene(
                        scene_number=2,
                        act_number=1,
                        title="The Whisper",
                        description="A child's whisper echoes from the doll.",
                        narration_text="The air turned ice-cold.",
                        target_clip_seconds=8.0,
                    ),
                ],
            ),
            Act(
                act_number=2,
                title="The Escalation",
                summary="The doll's influence spreads.",
                scenes=[
                    Scene(
                        scene_number=1,
                        act_number=2,
                        title="Mirror Cracks",
                        description="Every mirror in the house develops a hairline crack.",
                        narration_text="One by one, the mirrors began to crack.",
                        target_clip_seconds=8.0,
                    ),
                ],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Scene model
# ---------------------------------------------------------------------------


class TestScene:
    def test_valid_scene(self) -> None:
        s = Scene(scene_number=1, title="Test", description="A test scene")
        assert s.scene_number == 1
        assert s.act_number is None
        assert s.target_clip_seconds == 8.0

    def test_scene_number_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            Scene(scene_number=0, title="T", description="D")

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Scene(scene_number=1, title="T", description="D", unexpected="x")  # type: ignore[call-arg]

    def test_narration_seconds_must_be_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            Scene(scene_number=1, title="T", description="D", narration_seconds=-1)


# ---------------------------------------------------------------------------
# StoryDoc model
# ---------------------------------------------------------------------------


class TestStoryDoc:
    def test_total_scenes(self, sample_story_doc: StoryDoc) -> None:
        assert sample_story_doc.total_scenes == 3

    def test_all_scenes_flat_order(self, sample_story_doc: StoryDoc) -> None:
        scenes = sample_story_doc.all_scenes
        assert len(scenes) == 3
        assert [s.scene_number for s in scenes] == [1, 2, 1]

    def test_renumber_scenes(self, sample_story_doc: StoryDoc) -> None:
        # Scene numbers are per-act (2 acts: [1,2], [1]); renumber should make
        # them sequential across the whole story (1,2,3).
        sample_story_doc.renumber_scenes()
        numbers = [s.scene_number for s in sample_story_doc.all_scenes]
        assert numbers == [1, 2, 3]

    def test_acts_required(self) -> None:
        with pytest.raises(ValidationError):
            StoryDoc(topic="t", niche="n", target_seconds=10, title="T", logline="L", acts=[])

    def test_target_seconds_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            StoryDoc(
                topic="t", niche="n", target_seconds=0, title="T", logline="L",
                acts=[Act(act_number=1, title="A", scenes=[Scene(scene_number=1, title="S", description="D")])],
            )

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StoryDoc(
                topic="t", niche="n", target_seconds=10, title="T", logline="L",
                acts=[Act(act_number=1, title="A", scenes=[Scene(scene_number=1, title="S", description="D")])],
                extra_field="should_fail",  # type: ignore[call-arg]
            )

    def test_json_round_trip(self, sample_story_doc: StoryDoc) -> None:
        """Model must survive JSON serialization/deserialization (artifact persistence)."""
        data = sample_story_doc.model_dump_json()
        restored = StoryDoc.model_validate_json(data)
        assert restored.total_scenes == 3
        assert restored.all_scenes[0].title == "The Attic"
        assert restored.acts[1].title == "The Escalation"

    def test_json_compatible_with_artifact_storage(self, sample_story_doc: StoryDoc) -> None:
        """Verify the JSON is plain JSON-serializable (for file storage)."""
        raw = json.loads(sample_story_doc.model_dump_json())
        assert raw["topic"] == "haunted doll"
        assert raw["acts"][0]["scenes"][0]["narration_text"] is not None


# ---------------------------------------------------------------------------
# Character / CharacterBible
# ---------------------------------------------------------------------------


class TestCharacter:
    def test_valid_character(self) -> None:
        c = Character(name="Bob", appearance="Tall", clothing="Coat", props=["Hat"])
        assert c.name == "Bob"
        assert c.props == ["Hat"]

    def test_required_fields(self) -> None:
        for field in ("name", "appearance", "clothing"):
            kwargs = {"name": "X", "appearance": "A", "clothing": "C"}
            kwargs[field] = ""
            with pytest.raises(ValidationError):
                Character(**kwargs)  # type: ignore[call-arg]

    def test_props_default_empty(self) -> None:
        c = Character(name="X", appearance="A", clothing="C")
        assert c.props == []


class TestCharacterBible:
    def test_empty_bible_is_valid(self) -> None:
        bible = CharacterBible()
        assert bible.characters == []
        assert bible.notes is None

    def test_with_characters(self, sample_character_bible: CharacterBible) -> None:
        assert len(sample_character_bible.characters) == 1
        assert sample_character_bible.characters[0].name == "Mara"

    def test_json_round_trip(self, sample_character_bible: CharacterBible) -> None:
        data = sample_character_bible.model_dump_json()
        restored = CharacterBible.model_validate_json(data)
        assert restored.characters[0].name == "Mara"
        assert restored.characters[0].props == ["Rusted key", "Cracked mirror"]


# ---------------------------------------------------------------------------
# VisualBible
# ---------------------------------------------------------------------------


class TestVisualBible:
    def test_valid_visual_bible(self, sample_visual_bible: VisualBible) -> None:
        assert sample_visual_bible.color_palette == ["deep_red", "dark_blue", "black"]

    def test_defaults(self) -> None:
        vb = VisualBible(lighting="low", camera_style="steady")
        assert vb.color_palette == []
        assert vb.notes is None
        assert vb.aspect_ratio is None

    def test_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            VisualBible(color_palette=["red"], lighting="", camera_style="wide")

    def test_json_round_trip(self, sample_visual_bible: VisualBible) -> None:
        data = sample_visual_bible.model_dump_json()
        restored = VisualBible.model_validate_json(data)
        assert restored.color_palette == ["deep_red", "dark_blue", "black"]


# ---------------------------------------------------------------------------
# StoryEngine ABC contract
# ---------------------------------------------------------------------------


class TestStoryEngineABC:
    def test_cannot_instantiate_abc_directly(self) -> None:
        with pytest.raises(TypeError):
            StoryEngine()  # abstract methods not implemented

    def test_hermes_engine_is_subclass(self) -> None:
        assert issubclass(HermesStoryEngine, StoryEngine)

    def test_subclass_must_implement_all_methods(self) -> None:
        class IncompleteEngine(StoryEngine):
            def generate_story(self, topic: str, niche: str, target_seconds: int) -> StoryDoc:
                raise NotImplementedError

        with pytest.raises(TypeError):
            IncompleteEngine()  # still abstract: missing 2 methods


# ---------------------------------------------------------------------------
# HermesStoryEngine stub
# ---------------------------------------------------------------------------


class TestHermesStoryEngine:
    @pytest.fixture
    def engine(self) -> HermesStoryEngine:
        return HermesStoryEngine(template_dir=TEMPLATE_DIR)

    def test_load_template(self, engine: HermesStoryEngine) -> None:
        tpl = engine.load_template("horror")
        assert tpl["niche"] == "horror"
        assert tpl["story_structure"]["acts"] == 3
        assert "jump_scare" in tpl["scene_types"]
        assert "deep_red" in tpl["visual_guidance"]["color_palette"]

    def test_load_missing_template(self, engine: HermesStoryEngine) -> None:
        with pytest.raises(FileNotFoundError):
            engine.load_template("nonexistent_niche")

    def test_generate_story_returns_valid_story_doc(self, engine: HermesStoryEngine) -> None:
        story = engine.generate_story("haunted doll", "horror", 600)
        assert isinstance(story, StoryDoc)
        assert story.topic == "haunted doll"
        assert story.niche == "horror"
        assert story.target_seconds == 600
        assert story.total_scenes >= 1
        assert all(s.scene_number >= 1 for s in story.all_scenes)
        assert all(len(s.narration_text) > 0 for s in story.all_scenes)

    def test_generate_story_template_driven(self, engine: HermesStoryEngine) -> None:
        """Stub output should reflect template pacing from the horror template."""
        story = engine.generate_story("ghost child", "horror", 300)
        template = engine.load_template("horror")
        pacing = template["story_structure"]["pacing"]
        # The stub narration text includes the pacing value.
        assert pacing in story.all_scenes[0].narration_text

    def test_generate_character_bible_returns_valid_bible(self, engine: HermesStoryEngine) -> None:
        story = engine.generate_story("haunted doll", "horror", 600)
        bible = engine.generate_character_bible(story)
        assert isinstance(bible, CharacterBible)
        assert len(bible.characters) >= 1
        c = bible.characters[0]
        assert c.name
        assert c.appearance
        assert c.clothing

    def test_generate_visual_bible_uses_template(self, engine: HermesStoryEngine) -> None:
        story = engine.generate_story("haunted doll", "horror", 600)
        bible = engine.generate_character_bible(story)
        vb = engine.generate_visual_bible(story, bible)
        assert isinstance(vb, VisualBible)
        template_vg = engine.load_template("horror")["visual_guidance"]
        assert vb.color_palette == template_vg["color_palette"]
        assert vb.lighting == template_vg["lighting"]
        assert vb.camera_style == template_vg["camera_style"]
        assert vb.aspect_ratio == template_vg["recommended_aspect_ratio"]

    def test_full_pipeline_story_chain(self, engine: HermesStoryEngine) -> None:
        """The three generate_* methods form a valid pipeline chain."""
        story = engine.generate_story("abandoned house", "horror", 600)
        bible = engine.generate_character_bible(story)
        vb = engine.generate_visual_bible(story, bible)
        # All outputs are JSON-round-trippable (artifact persistence).
        story.model_validate_json(story.model_dump_json())
        bible.model_validate_json(bible.model_dump_json())
        vb.model_validate_json(vb.model_dump_json())


# ---------------------------------------------------------------------------
# Factory / registry seam
# ---------------------------------------------------------------------------


class TestStoryEngineFactory:
    def test_get_story_engine_default_uses_story_yaml(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """config/story.yaml has engine: hermes."""
        engine = get_story_engine()
        assert isinstance(engine, HermesStoryEngine)

    def test_get_story_engine_explicit_name(self) -> None:
        engine = get_story_engine("hermes")
        assert isinstance(engine, HermesStoryEngine)

    def test_unknown_engine_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown story engine"):
            get_story_engine("nonexistent")

    def test_register_and_resolve_custom_engine(self) -> None:
        """External LLM engines (OpenAI/Gemini) plug in via register_engine."""

        class DummyEngine(StoryEngine):
            def generate_story(self, topic: str, niche: str, target_seconds: int) -> StoryDoc:
                return StoryDoc(
                    topic=topic, niche=niche, target_seconds=target_seconds,
                    title="Dummy", logline="D",
                    acts=[Act(act_number=1, title="A", scenes=[Scene(scene_number=1, title="S", description="D")])],
                )

            def generate_character_bible(self, story: StoryDoc) -> CharacterBible:
                return CharacterBible()

            def generate_visual_bible(self, story: StoryDoc, character_bible: CharacterBible) -> VisualBible:
                return VisualBible(lighting="L", camera_style="C")

        register_engine("dummy", DummyEngine)
        try:
            engine = get_story_engine("dummy")
            assert isinstance(engine, DummyEngine)
        finally:
            # Clean up registry to avoid leaking test state.
            from app.story.engine import _ENGINE_REGISTRY
            _ENGINE_REGISTRY.pop("dummy", None)

    def test_factory_with_missing_config_falls_back_to_hermes(self, tmp_path: Path) -> None:
        engine = get_story_engine(config_path=tmp_path / "nonexistent.yaml")
        assert isinstance(engine, HermesStoryEngine)
