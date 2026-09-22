"""Unit tests for Scenes and Prompts modules."""
import json
import pytest
from app.scenes.planner import ScenePlanner, PlanarScene
from app.story.models import StoryDoc, Act, Scene as StoryScene, CharacterBible, VisualBible, Character


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def sample_story() -> StoryDoc:
    return StoryDoc(
        topic="haunted doll",
        niche="horror",
        target_seconds=600,
        title="The Haunted Doll",
        logline="A haunted doll awakens a darkness.",
        acts=[
            Act(
                act_number=1,
                title="Act I",
                summary="A doll arrives.",
                scenes=[
                    StoryScene(
                        scene_number=1,
                        title="The Arrival",
                        description="A doll is placed on a shelf by the door.",
                        narration_text="In the dim light, something stirs. A doll sits alone.",
                        target_clip_seconds=8.0,
                    ),
                    StoryScene(
                        scene_number=2,
                        title="First Night",
                        description="The protagonist hears whispers and the air grows colder.",
                        narration_text="That night, something whispers. The air grows colder.",
                        target_clip_seconds=8.0,
                    ),
                    StoryScene(
                        scene_number=3,
                        title="The Threat Revealed",
                        description="The doll's face has changed — the protagonist runs as darkness closes in.",
                        narration_text="The doll's face is different now. It knows. It watches. The protagonist runs as the darkness closes in.",
                        target_clip_seconds=8.0,
                    ),
                ],
            ),
        ],
    )


@pytest.fixture
def sample_characters() -> CharacterBible:
    return CharacterBible(
        characters=[
            Character(
                name="The Protagonist",
                appearance="Tall, dark hair, wears a dark jacket",
                clothing="Dark jacket, jeans, boots",
                props=["Flashlight", "Phone (dead battery)"],
            ),
        ],
        notes="One protagonist for testing.",
    )


@pytest.fixture
def sample_visual() -> VisualBible:
    return VisualBible(
        color_palette=["black", "deep_red"],
        lighting="low_contrast",
        camera_style="tight_closeups",
        aspect_ratio="9:16",
        notes="Horror visual bible.",
    )


# --------------------------------------------------------------------------- #
# ScenePlanner tests
# --------------------------------------------------------------------------- #

class TestScenePlanner:
    def test_compute_narration_seconds(self) -> None:
        planner = ScenePlanner()
        assert planner.compute_narration_seconds("hello world") == 2.0
        assert planner.compute_narration_seconds("a " * 250) == 100.0
        assert planner.compute_narration_seconds(None) is None
        assert planner.compute_narration_seconds("") is None  # empty → None, not 0.0

    def test_classify_complexity_low(self, sample_story: StoryDoc) -> None:
        planner = ScenePlanner()
        scene = sample_story.all_scenes[0]
        assert planner.classify_complexity(scene) == "LOW"

    def test_classify_complexity_medium(self, sample_story: StoryDoc) -> None:
        planner = ScenePlanner()
        scene = sample_story.all_scenes[1]
        assert planner.classify_complexity(scene) in ("LOW", "MEDIUM")

    def test_classify_complexity_high(self, sample_story: StoryDoc) -> None:
        planner = ScenePlanner()
        scene = sample_story.all_scenes[2]
        assert planner.classify_complexity(scene) in ("MEDIUM", "HIGH")

    def test_plan_produces_scenes(self, sample_story: StoryDoc,
                                   sample_characters: CharacterBible,
                                   sample_visual: VisualBible) -> None:
        planner = ScenePlanner()
        scenes = planner.plan(sample_story, sample_characters, sample_visual)
        assert len(scenes) == 3
        assert all(isinstance(s, PlanarScene) for s in scenes)

    def test_plan_narration_seconds(self, sample_story: StoryDoc,
                                      sample_characters: CharacterBible,
                                      sample_visual: VisualBible) -> None:
        planner = ScenePlanner()
        scenes = planner.plan(sample_story, sample_characters, sample_visual)
        for s in scenes:
            assert s.narration_seconds is not None
            assert s.narration_seconds > 0

    def test_plan_continuity_dna(self, sample_story: StoryDoc,
                                  sample_characters: CharacterBible,
                                  sample_visual: VisualBible) -> None:
        planner = ScenePlanner()
        scenes = planner.plan(sample_story, sample_characters, sample_visual)
        for s in scenes:
            dna = json.loads(s.continuity_dna)
            assert "scene_index" in dna
            assert "characters" in dna
            assert "visual_anchors" in dna

    def test_plan_visual_anchors(self, sample_story: StoryDoc,
                                  sample_characters: CharacterBible,
                                  sample_visual: VisualBible) -> None:
        planner = ScenePlanner()
        scenes = planner.plan(sample_story, sample_characters, sample_visual)
        dna = json.loads(scenes[0].continuity_dna)
        assert dna["visual_anchors"]["color_palette"] == ["black", "deep_red"]
        assert dna["visual_anchors"]["lighting"] == "low_contrast"
        assert dna["visual_anchors"]["camera_style"] == "tight_closeups"
        assert dna["visual_anchors"]["aspect_ratio"] == "9:16"

    def test_plan_character_anchors(self, sample_story: StoryDoc,
                                     sample_characters: CharacterBible,
                                     sample_visual: VisualBible) -> None:
        planner = ScenePlanner()
        scenes = planner.plan(sample_story, sample_characters, sample_visual)
        dna = json.loads(scenes[0].continuity_dna)
        assert len(dna["characters"]) == 1
        assert dna["characters"][0]["name"] == "The Protagonist"

    def test_plan_scene_ids_sequential(self, sample_story: StoryDoc,
                                        sample_characters: CharacterBible,
                                        sample_visual: VisualBible) -> None:
        planner = ScenePlanner()
        scenes = planner.plan(sample_story, sample_characters, sample_visual)
        assert scenes[0].scene_id == "scene-001"
        assert scenes[1].scene_id == "scene-002"
        assert scenes[2].scene_id == "scene-003"


class TestPlanarScene:
    def test_basic_fields(self) -> None:
        s = PlanarScene(
            scene_id="s1",
            scene_number=1,
            act_number=1,
            title="Test",
            description="A test scene",
            narration_text="Test narration",
            narration_seconds=5.0,
            target_clip_seconds=8.0,
            complexity="LOW",
            continuity_dna=json.dumps({"test": True}),
            narration={"text": "Test", "seconds": 5.0, "style": "standard"},
        )
        assert s.scene_id == "s1"
        assert s.complexity == "LOW"
        assert json.loads(s.continuity_dna)["test"] is True

    def test_narration_seconds_none(self) -> None:
        s = PlanarScene(
            scene_id="s1",
            scene_number=1,
            act_number=None,
            title="Test",
            description="A test",
            narration_text=None,
            narration_seconds=None,
            target_clip_seconds=8.0,
            complexity="LOW",
            continuity_dna="{}",
            narration={"text": None, "seconds": None, "style": "standard"},
        )
        assert s.narration_seconds is None
