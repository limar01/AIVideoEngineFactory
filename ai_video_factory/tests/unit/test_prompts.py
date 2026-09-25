"""Unit tests for the prompts module (PromptCompiler + adapters).

Tests the new prompt compiler interface:
- SnapGenPromptAdapter.format_prompt(scene, continuity_dna)
- SnapGenPromptAdapter.get_negative_prompt(scene)
- PromptCompiler.compile(scene)
- PromptCompiler.compile_multi(scenes, ...)
"""

from __future__ import annotations

import json
import pytest

from app.prompts.compiler import (
    PromptCompiler,
    SnapGenPromptAdapter,
    CompiledPrompt,
    _optimize_description,
)
from app.scenes.planner import PlanarScene


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
                "color_palette": ["deep_red", "black"],
                "lighting": "low_contrast",
                "camera_style": "tight_closeup",
                "aspect_ratio": "9:16",
            },
        }),
        narration={"text": "In the dim light...", "seconds": 4.8, "style": "standard"},
        prompts=[],
    )


@pytest.fixture
def sample_scene_high() -> PlanarScene:
    return PlanarScene(
        scene_id="scene-002",
        scene_number=2,
        act_number=1,
        title="Confrontation",
        description="The protagonist runs through the hallway while the doll chases her, "
                    "simultaneously the lights flicker and a door slams.",
        narration_text="She runs. The doll follows. Lights flicker.",
        narration_seconds=6.0,
        target_clip_seconds=8.0,
        complexity="HIGH",
        continuity_dna=json.dumps({
            "scene_index": 1,
            "characters": [],
            "visual_anchors": {
                "color_palette": ["red", "black"],
                "lighting": "flickering",
                "camera_style": "handheld_shaky",
                "aspect_ratio": "9:16",
            },
        }),
        narration={"text": "She runs...", "seconds": 6.0, "style": "standard"},
        prompts=[],
    )


@pytest.fixture
def adapter() -> SnapGenPromptAdapter:
    return SnapGenPromptAdapter()


# ---------------------------------------------------------------------------
# SnapGenPromptAdapter
# ---------------------------------------------------------------------------


class TestSnapGenPromptAdapter:
    def test_format_prompt_basic(self, adapter: SnapGenPromptAdapter, sample_scene: PlanarScene) -> None:
        prompt = adapter.format_prompt(sample_scene)
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "cinematic" in prompt.lower() or "shot" in prompt.lower()

    def test_format_prompt_injects_continuity(self, adapter: SnapGenPromptAdapter, sample_scene: PlanarScene) -> None:
        prompt = adapter.format_prompt(sample_scene)
        assert len(prompt) > 50  # Should have substantial content

    def test_format_prompt_includes_character(self, adapter: SnapGenPromptAdapter, sample_scene: PlanarScene) -> None:
        prompt = adapter.format_prompt(sample_scene)
        # Check character info is in prompt
        assert "character" in prompt.lower() or "Protagonist" in prompt

    def test_format_prompt_sets_aspect_ratio(self, adapter: SnapGenPromptAdapter, sample_scene: PlanarScene) -> None:
        prompt = adapter.format_prompt(sample_scene)
        assert "9:16" in prompt

    def test_format_prompt_sets_resolution(self, adapter: SnapGenPromptAdapter, sample_scene: PlanarScene) -> None:
        prompt = adapter.format_prompt(sample_scene)
        assert "1080p" in prompt

    def test_format_prompt_sets_duration(self, adapter: SnapGenPromptAdapter, sample_scene: PlanarScene) -> None:
        prompt = adapter.format_prompt(sample_scene)
        assert "8" in prompt  # 8 seconds

    def test_format_prompt_dialouge_in_prompt(self, adapter: SnapGenPromptAdapter, sample_scene: PlanarScene) -> None:
        prompt = adapter.format_prompt(sample_scene)
        # Veo generates audio from dialogue in prompt
        assert "audio" in prompt.lower() or "dialogue" in prompt.lower()

    def test_get_negative_prompt(self, adapter: SnapGenPromptAdapter, sample_scene: PlanarScene) -> None:
        neg = adapter.get_negative_prompt(sample_scene)
        assert isinstance(neg, str)
        assert len(neg) > 0
        assert "--no:" in neg

    def test_get_negative_prompt_prevents_inconsistency(self, adapter: SnapGenPromptAdapter, sample_scene: PlanarScene) -> None:
        neg = adapter.get_negative_prompt(sample_scene)
        assert "morphing" in neg
        assert "inconsistent" in neg


# ---------------------------------------------------------------------------
# _optimize_description helper
# ---------------------------------------------------------------------------


class TestOptimizeDescription:
    def test_basic_description_unchanged(self) -> None:
        result = _optimize_description("A doll sits on a shelf.", "LOW")
        assert result == "A doll sits on a shelf."

    def test_removes_simultaneous_while(self) -> None:
        result = _optimize_description("A runs while B talks.", "LOW")
        assert "and then" in result
        assert "while" not in result

    def test_removes_meanwhile(self) -> None:
        result = _optimize_description("A walks meanwhile B watches.", "LOW")
        assert "and then" in result

    def test_high_complexity_adds_focus(self) -> None:
        result = _optimize_description("Complex scene with many actions.", "HIGH")
        assert "Focus on one clear action:" in result

    def test_description_truncated_long(self) -> None:
        long_desc = "word " * 300
        result = _optimize_description(long_desc, "LOW")
        assert len(result) <= 200


# ---------------------------------------------------------------------------
# PromptCompiler
# ---------------------------------------------------------------------------


class TestPromptCompiler:
    def test_compile_produces_prompt(self, sample_scene: PlanarScene) -> None:
        compiler = PromptCompiler(provider="snapgen")
        prompt = compiler.compile(sample_scene)
        assert isinstance(prompt, CompiledPrompt)
        assert prompt.scene_id == "scene-001"
        assert prompt.provider == "snapgen"

    def test_compile_prompt_text_nonempty(self, sample_scene: PlanarScene) -> None:
        compiler = PromptCompiler(provider="snapgen")
        prompt = compiler.compile(sample_scene)
        assert len(prompt.prompt_text) > 0

    def test_compile_sets_version(self, sample_scene: PlanarScene) -> None:
        compiler = PromptCompiler(provider="snapgen")
        prompt = compiler.compile(sample_scene)
        assert prompt.version == 1

    def test_compile_metadata_has_continuity(self, sample_scene: PlanarScene) -> None:
        compiler = PromptCompiler(provider="snapgen")
        prompt = compiler.compile(sample_scene)
        assert "continuity_dna" in prompt.metadata

    def test_compile_metadata_has_target_clip(self, sample_scene: PlanarScene) -> None:
        compiler = PromptCompiler(provider="snapgen")
        prompt = compiler.compile(sample_scene)
        assert prompt.metadata.get("target_clip_seconds") == 8.0

    def test_compile_with_custom_adapter(self, sample_scene: PlanarScene) -> None:
        adapter = SnapGenPromptAdapter()
        compiler = PromptCompiler(provider="snapgen", adapter=adapter)
        prompt = compiler.compile(sample_scene)
        assert isinstance(prompt, CompiledPrompt)

    def test_compile_all(self, sample_scene: PlanarScene, sample_scene_high: PlanarScene) -> None:
        compiler = PromptCompiler(provider="snapgen")
        scenes = [sample_scene, sample_scene_high]
        prompts = compiler.compile(scene=scenes)
        assert len(prompts) == 2
        assert all(isinstance(p, CompiledPrompt) for p in prompts)

    def test_compile_single_vs_multi(self, sample_scene: PlanarScene) -> None:
        compiler = PromptCompiler(provider="snapgen")
        # Single
        single = compiler.compile(sample_scene)
        assert isinstance(single, CompiledPrompt)
        # Multi (list)
        multi = compiler.compile([sample_scene])
        assert isinstance(multi, list)
        assert len(multi) == 1


# ---------------------------------------------------------------------------
# CompiledPrompt properties
# ---------------------------------------------------------------------------


class TestCompiledPromptProperties:
    def test_scene_id(self) -> None:
        cp = CompiledPrompt(scene_id="s1", scene_number=1, provider="snapgen", prompt_text="test")
        assert cp.scene_id == "s1"

    def test_scene_number(self) -> None:
        cp = CompiledPrompt(scene_id="s1", scene_number=5, provider="snapgen", prompt_text="test")
        assert cp.scene_number == 5

    def test_provider(self) -> None:
        cp = CompiledPrompt(scene_id="s1", scene_number=1, provider="snapgen", prompt_text="test")
        assert cp.provider == "snapgen"

    def test_text_property(self) -> None:
        cp = CompiledPrompt(scene_id="s1", scene_number=1, provider="snapgen", prompt_text="hello")
        assert cp.text == "hello"

    def test_clip_seconds_from_metadata(self, sample_scene: PlanarScene) -> None:
        compiler = PromptCompiler(provider="snapgen")
        prompt = compiler.compile(sample_scene)
        assert prompt.clip_seconds == 8.0


# ---------------------------------------------------------------------------
# End-to-end: story scene → prompt
# ---------------------------------------------------------------------------


class TestEndToEndPromptPipeline:
    def test_full_pipeline_produces_prompts(self) -> None:
        """Story scene → PleanarScene → compiled prompt."""
        from app.story.engine import PinoyDramaStoryEngine
        from app.scenes.planner import ScenePlanner
        from app.prompts.compiler import PromptCompiler, SnapGenPromptAdapter

        engine = PinoyDramaStoryEngine()
        story = engine.generate_story("family conflict", "pinoy_drama", 480)
        cb = engine.generate_character_bible(story)
        vb = engine.generate_visual_bible(story, cb)

        planner = ScenePlanner()
        scenes = planner.plan(story, cb, vb)
        assert len(scenes) > 0

        adapter = SnapGenPromptAdapter()
        compiler = PromptCompiler(provider="snapgen", adapter=adapter)
        prompts = compiler.compile(scenes)

        assert len(prompts) == len(scenes)
        assert all(len(p.prompt_text) > 0 for p in prompts)
        assert all(p.provider == "snapgen" for p in prompts)
