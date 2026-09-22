"""Unit tests for the prompts module (PromptCompiler + adapters)."""
import json

import pytest

from app.prompts.compiler import (
    PromptCompiler,
    SnapGenPromptAdapter,
    CompiledPrompt,
    get_prompt_adapter,
    _optimize_description,
)
from app.scenes.planner import PlanarScene


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def sample_scene() -> PlanarScene:
    return PlanarScene(
        scene_id="scene-001",
        scene_number=1,
        act_number=1,
        title="The Arrival",
        description="A haunted doll is placed on a shelf in a dark hallway.",
        narration_text="In the dim light, something stirs. A doll sits alone.",
        narration_seconds=4.8,
        target_clip_seconds=8.0,
        complexity="LOW",
        continuity_dna=json.dumps({
            "scene_index": 0,
            "characters": [
                {
                    "name": "The Protagonist",
                    "appearance": "Tall, dark hair",
                    "clothing": "Dark jacket",
                    "props": ["Flashlight"],
                },
            ],
            "visual_anchors": {
                "color_palette": ["black", "deep_red"],
                "lighting": "low_contrast",
                "camera_style": "tight_closeups",
                "aspect_ratio": "9:16",
            },
        }),
        narration={"text": "In the dim light, something stirs. A doll sits alone.", "seconds": 4.8, "style": "standard"},
    )


@pytest.fixture
def sample_scene_high() -> PlanarScene:
    return PlanarScene(
        scene_id="scene-002",
        scene_number=2,
        act_number=1,
        title="First Night",
        description="The protagonist walks down the hall while the doll's eyes follow and the lights flicker.",
        narration_text="That night, something whispers. The air grows colder.",
        narration_seconds=3.2,
        target_clip_seconds=8.0,
        complexity="HIGH",
        continuity_dna=json.dumps({
            "scene_index": 1,
            "characters": [
                {"name": "The Protagonist", "appearance": "Tall, dark hair", "clothing": "Dark jacket", "props": ["Flashlight"]},
                {"name": "The Doll", "appearance": "Porcelain face", "clothing": "Black dress", "props": []},
            ],
            "visual_anchors": {
                "color_palette": ["black", "deep_red"],
                "lighting": "low_contrast",
                "camera_style": "tight_closeups",
                "aspect_ratio": "9:16",
            },
        }),
        narration={"text": "That night, something whispers. The air grows colder.", "seconds": 3.2, "style": "standard"},
    )


# --------------------------------------------------------------------------- #
# PromptCompiler unit tests
# --------------------------------------------------------------------------- #

class TestPromptCompiler:
    def test_compile_produces_prompt(self, sample_scene: PlanarScene) -> None:
        compiler = PromptCompiler(provider="snapgen")
        prompt = compiler.compile(sample_scene)
        assert isinstance(prompt, CompiledPrompt)
        assert prompt.provider == "snapgen"
        assert prompt.version == 1
        assert prompt.scene_id == "scene-001"
        assert prompt.scene_number == 1

    def test_compile_prompt_text_nonempty(self, sample_scene: PlanarScene) -> None:
        compiler = PromptCompiler(provider="snapgen")
        prompt = compiler.compile(sample_scene)
        assert len(prompt.prompt_text) > 0
        assert "Aspect ratio: 9:16" in prompt.prompt_text
        assert "Resolution: 720p" in prompt.prompt_text
        assert "Duration: ~8.0s" in prompt.prompt_text

    def test_compile_injects_visual_anchors(self, sample_scene: PlanarScene) -> None:
        compiler = PromptCompiler(provider="snapgen")
        prompt = compiler.compile(sample_scene)
        assert "low_contrast" in prompt.prompt_text
        assert "tight_closeups" in prompt.prompt_text
        assert "black" in prompt.prompt_text
        assert "deep_red" in prompt.prompt_text

    def test_compile_injects_characters(self, sample_scene: PlanarScene) -> None:
        compiler = PromptCompiler(provider="snapgen")
        prompt = compiler.compile(sample_scene)
        assert "The Protagonist" in prompt.prompt_text
        assert "Dark jacket" in prompt.prompt_text

    def test_compile_continuity_injection(self, sample_scene: PlanarScene) -> None:
        compiler = PromptCompiler(provider="snapgen")
        prompt = compiler.compile(sample_scene)
        # Continuity should be injected at end
        assert "[Maintain consistency:" in prompt.prompt_text
        assert "The Protagonist in Dark jacket" in prompt.prompt_text

    def test_compile_all(self, sample_scene: PlanarScene, sample_scene_high: PlanarScene) -> None:
        compiler = PromptCompiler(provider="snapgen")
        prompts = compiler.compile_all([sample_scene, sample_scene_high])
        assert len(prompts) == 2
        assert prompts[0].scene_id == "scene-001"
        assert prompts[1].scene_id == "scene-002"

    def test_compile_all_different_providers(self, sample_scene: PlanarScene) -> None:
        compiler = PromptCompiler(provider="snapgen")
        prompts = compiler.compile_all([sample_scene])
        assert prompts[0].provider == "snapgen"

    def test_compile_metadata(self, sample_scene: PlanarScene) -> None:
        compiler = PromptCompiler(provider="snapgen")
        prompt = compiler.compile(sample_scene)
        assert prompt.metadata["complexity"] == "LOW"
        assert prompt.metadata["narration_seconds"] == 4.8
        assert prompt.metadata["target_clip_seconds"] == 8.0
        assert "continuity_dna" in prompt.metadata

    def test_complexity_weight_low(self, sample_scene: PlanarScene) -> None:
        compiler = PromptCompiler(provider="snapgen")
        prompt = compiler.compile(sample_scene)
        assert "Focus on one clear action" not in prompt.prompt_text

    def test_complexity_weight_high(self, sample_scene_high: PlanarScene) -> None:
        compiler = PromptCompiler(provider="snapgen")
        prompt = compiler.compile(sample_scene_high)
        assert "Focus on one clear action" in prompt.prompt_text

    def test_high_complexity_simplifies_actions(self, sample_scene_high: PlanarScene) -> None:
        compiler = PromptCompiler(provider="snapgen")
        prompt = compiler.compile(sample_scene_high)
        assert "while" not in prompt.prompt_text.lower()
        assert "and then" in prompt.prompt_text

    def test_get_prompt_adapter_unknown(self) -> None:
        adapter = get_prompt_adapter("unknown_provider")
        assert isinstance(adapter, SnapGenPromptAdapter)

    def test_get_prompt_adapter_snapgen(self) -> None:
        adapter = get_prompt_adapter("snapgen")
        assert isinstance(adapter, SnapGenPromptAdapter)

    def test_create_repaired_prompt(self, sample_scene: PlanarScene) -> None:
        compiler = PromptCompiler(provider="snapgen")
        original = compiler.compile(sample_scene)
        repaired = compiler.create_repaired_prompt(
            original,
            "A haunted doll sits on a shelf.",
            new_version=2,
        )
        assert repaired.version == 2
        assert repaired.scene_id == "scene-001"
        assert repaired.provider == "snapgen"
        assert "haunted doll" in repaired.prompt_text.lower()
        assert repaired.metadata["repair_strategy"] == "simplify_description"
        assert repaired.metadata["complexity"] == "LOW"

    def test_create_repaired_prompt_preserves_continuity(self, sample_scene: PlanarScene) -> None:
        compiler = PromptCompiler(provider="snapgen")
        original = compiler.compile(sample_scene)
        repaired = compiler.create_repaired_prompt(
            original,
            "A doll sits on a shelf.",
            new_version=2,
        )
        # Continuity should still be in the repaired prompt
        assert "The Protagonist" in repaired.prompt_text
        assert "Dark jacket" in repaired.prompt_text


class TestSnapGenPromptAdapter:
    def test_format_prompt_basic(self, sample_scene: PlanarScene) -> None:
        adapter = SnapGenPromptAdapter()
        result = adapter.format_prompt(sample_scene)
        assert isinstance(result, str)
        assert len(result) > 0
        assert "Aspect ratio: 9:16" in result

    def test_format_prompt_injects_continuity(self, sample_scene: PlanarScene) -> None:
        adapter = SnapGenPromptAdapter()
        dna = json.loads(sample_scene.continuity_dna)
        result = adapter.format_prompt(sample_scene, dna)
        assert "The Protagonist" in result
        assert "Dark jacket" in result

    def test_inject_continuity_no_characters(self) -> None:
        adapter = SnapGenPromptAdapter()
        result = adapter.inject_continuity("A simple scene.", {})
        assert result == "A simple scene."

    def test_inject_continuity_with_characters(self) -> None:
        adapter = SnapGenPromptAdapter()
        dna = {
            "characters": [
                {"name": "Hero", "appearance": "Tall", "clothing": "Red coat", "props": ["Sword"]}
            ]
        }
        result = adapter.inject_continuity("The hero walks.", dna)
        assert "Maintain consistency:" in result
        assert "Hero in Red coat" in result

    def test_complexity_weight(self, sample_scene: PlanarScene) -> None:
        adapter = SnapGenPromptAdapter()
        assert adapter.complexity_weight(sample_scene) == "LOW"

    def test_custom_aspect_ratio(self) -> None:
        adapter = SnapGenPromptAdapter(aspect_ratio="16:9", resolution="1080p")
        scene = PlanarScene(
            scene_id="s1", scene_number=1, act_number=None,
            title="Test", description="Test",
            narration_text=None, narration_seconds=None,
            target_clip_seconds=8.0, complexity="LOW",
            continuity_dna="{}",
            narration={"text": None, "seconds": None, "style": "standard"},
        )
        result = adapter.format_prompt(scene)
        assert "Aspect ratio: 16:9" in result
        assert "Resolution: 1080p" in result


class TestOptimizeDescription:
    def test_removes_simultaneous_connectors(self) -> None:
        text = "A runs while B talks — simultaneously."
        result = _optimize_description(text, "MEDIUM")
        assert "while" not in result.lower()
        assert "simultaneously" not in result.lower()
        assert "and then" in result.lower()

    def test_keeps_simple_descriptions(self) -> None:
        text = "A haunted doll sits on a shelf."
        result = _optimize_description(text, "LOW")
        assert result == text

    def test_high_complexity_prefixed(self) -> None:
        text = "A runs. B walks. C talks."
        result = _optimize_description(text, "HIGH")
        assert result.startswith("Focus on one clear action:")
        assert "A runs" in result

    def test_truncates_long_descriptions(self) -> None:
        text = "word " * 300
        result = _optimize_description(text, "LOW")
        assert len(result) <= 200


class TestEndToEndPromptPipeline:
    """Full pipeline: story → scene planner → prompt compiler."""

    def test_full_pipeline_produces_prompts(self) -> None:
        from app.story.models import StoryDoc, Act, Scene as StoryScene, CharacterBible, VisualBible, Character

        story = StoryDoc(
            topic="haunted doll",
            niche="horror",
            target_seconds=600,
            title="The Haunted Doll",
            logline="A haunted doll.",
            acts=[
                Act(
                    act_number=1,
                    title="Act I",
                    scenes=[
                        StoryScene(
                            scene_number=1,
                            title="Opening",
                            description="A haunted doll sits on a shelf in a dark hallway.",
                            narration_text="In the dim light, something stirs.",
                            target_clip_seconds=8.0,
                        ),
                    ],
                ),
            ],
        )

        characters = CharacterBible(characters=[
            Character(
                name="The Protagonist",
                appearance="Tall, dark hair",
                clothing="Dark jacket",
                props=["Flashlight"],
            )
        ])

        visual = VisualBible(
            color_palette=["black", "deep_red"],
            lighting="low_contrast",
            camera_style="tight_closeups",
            aspect_ratio="9:16",
        )

        from app.scenes.planner import ScenePlanner
        planner = ScenePlanner()
        scenes = planner.plan(story, characters, visual)

        assert len(scenes) == 1
        assert scenes[0].narration_seconds == 2.4  # "In the dim light, something stirs." ≈ 3 words at 150wpm = 2.0s, min_clipped to 2.0

        compiler = PromptCompiler(provider="snapgen")
        prompts = compiler.compile_all(scenes)

        assert len(prompts) == 1
        assert prompts[0].provider == "snapgen"
        assert "Aspect ratio: 9:16" in prompts[0].prompt_text
        assert "The Protagonist" in prompts[0].prompt_text
        assert "Dark jacket" in prompts[0].prompt_text
        assert "Flashlight" in prompts[0].metadata["continuity_dna"]
