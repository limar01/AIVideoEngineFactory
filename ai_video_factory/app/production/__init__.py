"""Production Director — orchestrates the full Pinoy Kanto Shorts Drama pipeline.

Reads a user topic, runs story → character bible → visual bible → scenes →
continuity → prompts → QA gates → queue → generate → QA → repair → assemble.

Operates the existing components (StoryEngine, ScenePlanner, PromptCompiler,
GenerationQueue, VideoAssembler) as one coherent flow with gates between stages.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.core.config import get_config
from app.core.database import get_session
from sqlmodel import select
from app.core.models import GenerationJob, JobState, Project, ProjectStatus, Prompt as DBPrompt, Scene as DBS_cene
from app.prompts.compiler import CompiledPrompt, PromptCompiler
from app.providers.base import GenerationResult, VideoGenerationProvider
from app.providers.registry import create_provider
from app.queue.service import GenerationQueue
from app.scenes.optimizer import SceneOptimizer
from app.scenes.planner import PlanarScene, ScenePlanner
from app.story.engine import StoryEngine, get_story_engine
from app.story.models import CharacterBible, StoryDoc, VisualBible

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Gates (validation before each major stage)
# ---------------------------------------------------------------------------


class PromptPlaceholderError(ValueError):
    """Raised when a compiled prompt contains unresolved placeholders."""


PLACEHOLDER_PATTERNS = [
    "[CHARACTER]", "[LOCATION]", "[ACTION]", "[EMOTION]", "[DIALOGUE]",
    "[CAMERA]", "[LIGHTING]", "[PROPS]", "[WARDROBE]", "[ACCESSORIES]",
    "{character}", "{location}", "{action}", "{emotion}",
    "same person", "same character", "as before", "as in previous scene",
    "[INSERT", "{INSERT", "{{", "}}",
]


def validate_prompt_no_placeholders(prompt_text: str, scene_id: str) -> list[str]:
    """Check a compiled prompt for unresolved placeholders.

    Returns a list of found placeholder strings (empty = clean).
    Raises PromptPlaceholderError if any are found.
    """
    found: list[str] = []
    text_lower = prompt_text.lower()
    for pattern in PLACEHOLDER_PATTERNS:
        if pattern.lower() in text_lower:
            found.append(pattern)
    if found:
        raise PromptPlaceholderError(
            f"Scene {scene_id}: prompt contains unresolved placeholders: {found}. "
            f"Prompt text (first 200 chars): {prompt_text[:200]}"
        )
    return found


class StoryQualityGate:
    """Validates a StoryDoc before it enters the generation pipeline.

    Checks:
    - Has a title
    - Has at least one scene
    - First scene has a hook (not just exposition)
    - Scenes have descriptions
    - Dialogue fits within clip duration (rough estimate)
    """

    # Rough speaking pace: ~150 words/minute for Taglish conversational
    WORDS_PER_SECOND = 2.5

    def __init__(self, min_scenes: int = 2, max_scenes: int = 60):
        self.min_scenes = min_scenes
        self.max_scenes = max_scenes

    def validate(self, story: StoryDoc) -> dict[str, Any]:
        """Validate story and return issues list. Empty list = pass."""
        issues: list[dict[str, Any]] = []

        if not story.title or len(story.title.strip()) < 3:
            issues.append({
                "severity": "error",
                "check": "title",
                "message": f"Story title too short or empty: '{story.title}'",
            })

        if story.total_scenes < self.min_scenes:
            issues.append({
                "severity": "error",
                "check": "scene_count",
                "message": f"Only {story.total_scenes} scenes — need at least {self.min_scenes}",
            })

        if story.total_scenes > self.max_scenes:
            issues.append({
                "severity": "warning",
                "check": "scene_count",
                "message": f"{story.total_scenes} scenes exceeds cap of {self.max_scenes}",
            })

        # Check first scene has a hook
        first = story.all_scenes[0] if story.all_scenes else None
        if first:
            first_desc = (first.description or "").lower()
            boring_openers = ["this is", "there was", "once upon", "introduction",
                              "the story begins", "in this story"]
            if any(op in first_desc for op in boring_openers):
                issues.append({
                    "severity": "warning",
                    "check": "hook",
                    "message": f"Scene 1 may not hook immediately: '{first.description[:80]}...'",
                })

        # Dialogue timing: each scene's dialogue should fit in clip duration
        for scene in story.all_scenes:
            dialogue = getattr(scene, "dialogue_lines", None) or []
            clip_secs = getattr(scene, "target_clip_seconds", 8.0) or 8.0
            if dialogue:
                total_words = sum(len(text.split()) for _, text in dialogue)
                est_seconds = total_words / self.WORDS_PER_SECOND
                if est_seconds > clip_secs * 0.8:  # dialogue should use <80% of clip
                    issues.append({
                        "severity": "warning",
                        "check": "dialogue_timing",
                        "message": (
                            f"Scene {scene.scene_number} '{scene.title}': "
                            f"~{est_seconds:.1f}s of dialogue in {clip_secs}s clip "
                            f"({total_words} words). Consider shortening."
                        ),
                    })

        # Check scenes have descriptions
        for scene in story.all_scenes:
            if not scene.description or len(scene.description.strip()) < 10:
                issues.append({
                    "severity": "error",
                    "check": "scene_description",
                    "message": f"Scene {scene.scene_number} has empty or very short description",
                })

        return issues


# ---------------------------------------------------------------------------
# Production Director
# ---------------------------------------------------------------------------


class ProductionDirector:
    """Orchestrates a full Pinoy Kanto Shorts Drama production.

    Pipeline:
        configure → story → character bible → visual bible →
        scenes → complexity optimize → continuity → compile prompts →
        prompt QA gate → story quality gate → queue jobs →
        (generation happens asynchronously) →
        QA clips → repair failed → assemble → deliver

    Usage:
        director = ProductionDirector(provider="google_flow")
        report = director.run(topic="ang_nawawalang_pitaka", target_seconds=60)
    """

    def __init__(
        self,
        provider: str = "google_flow",
        story_engine_name: str | None = None,
        output_dir: str | Path = "output",
        project_name: str | None = None,
    ):
        self.provider_name = provider
        # Normalize provider name: registry uses hyphens (google-flow), user may pass underscores
        self._provider_registry_key = provider.replace("_", "-")
        self.story_engine_name = story_engine_name
        self.output_dir = Path(output_dir)
        self.project_name = project_name or f"pinoy_kanto_{provider}"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Sub-components — initialized during run()
        self.session: Any = None
        self.story_engine: StoryEngine | None = None
        self.story: StoryDoc | None = None
        self.character_bible: CharacterBible | None = None
        self.visual_bible: VisualBible | None = None
        self.planner: ScenePlanner | None = None
        self.optimizer: SceneComplexityOptimizer | None = None
        self.compiler: PromptCompiler | None = None
        self.queue: GenerationQueue | None = None
        self.provider: VideoGenerationProvider | None = None

        # Production state
        self.production_state: dict[str, Any] = {
            "project": {},
            "story": {},
            "characters": {},
            "visual_bible": {},
            "scenes": [],
            "continuity": {},
            "generation_jobs": [],
            "qa_results": [],
            "audio": {},
            "assembly": {},
            "final_output": {},
        }

        # Turn tracking (for kanban-style multi-turn ops)
        self.current_turn: int = 0
        self.turn_results: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Main entry points
    # ------------------------------------------------------------------

    def run(self, topic: str, target_seconds: int = 60, **kwargs: Any) -> dict[str, Any]:
        """Run the full production pipeline end-to-end.

        Args:
            topic: User's story topic (e.g. "ang_nawawalang_pitaka")
            target_seconds: Total video duration in seconds
            **kwargs: Passed to configure()

        Returns:
            Production report dict.
        """
        self.configure(topic=topic, target_seconds=target_seconds, **kwargs)
        self.turn("configure", self._do_configure)

        if not self._gate_configure():
            return self._build_report(failed_at="configure")

        self.turn("story", self._do_story)
        if not self._gate_story():
            return self._build_report(failed_at="story")

        self.turn("character_bible", self._do_character_bible)
        self.turn("visual_bible", self._do_visual_bible)
        self.turn("scenes", self._do_scenes)
        self.turn("complexity", self._do_complexity_optimize)
        self.turn("continuity", self._do_continuity)
        self.turn("compile_prompts", self._do_compile_prompts)

        if not self._gate_prompts():
            return self._build_report(failed_at="prompts")

        if not self._gate_story_quality():
            logger.warning("Story quality gate has warnings — continuing anyway")

        self.turn("queue_jobs", self._do_queue_jobs)

        # Generation is async — caller polls or waits
        logger.info("Production pipeline ready for generation. %d jobs queued.",
                    len(self.production_state["generation_jobs"]))

        return self._build_report(status="ready_to_generate")

    def turn(self, label: str, fn: Any) -> dict[str, Any]:
        """Run one pipeline stage with logging."""
        self.current_turn = label
        logger.info("=== TURN: %s ===", label)
        try:
            result = fn()
            self.turn_results.append({"turn": label, "status": "ok", "result": result})
            logger.info("TURN %s: OK", label)
            return result
        except Exception as exc:
            logger.error("TURN %s: FAILED — %s", label, exc)
            self.turn_results.append({"turn": label, "status": "failed", "error": str(exc)})
            raise

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def configure(self, topic: str, target_seconds: int = 60, **kwargs: Any) -> None:
        """Set up project configuration."""
        self.topic = topic
        self.target_seconds = target_seconds
        self.project_name = kwargs.pop("project_name", f"pinoy_kanto_{topic}")
        self.output_dir = Path(kwargs.pop("output_dir", "output"))
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Provider config
        provider_config = get_config("providers", self.provider_name) or {}
        self.clip_duration = provider_config.get("clip_duration", 10.0)
        self.resolution = provider_config.get("resolution", "1080p")
        self.aspect_ratio = provider_config.get("aspect_ratio", "9:16")

        # Story engine
        engine_name = kwargs.pop("story_engine", self.story_engine_name or "pinoy_drama")
        self.story_engine = get_story_engine(engine_name)

        logger.info(
            "Configured: provider=%s, topic=%s, target=%ds, "
            "clip=%ss, resolution=%s, aspect=%s, engine=%s",
            self.provider_name, topic, target_seconds,
            self.clip_duration, self.resolution, self.aspect_ratio,
            engine_name,
        )

    def _do_configure(self) -> dict[str, Any]:
        """Record configuration in production state."""
        self.production_state["project"] = {
            "name": self.project_name,
            "topic": self.topic,
            "target_seconds": self.target_seconds,
            "provider": self.provider_name,
            "clip_duration": self.clip_duration,
            "resolution": self.resolution,
            "aspect_ratio": self.aspect_ratio,
            "template": "pinoy_kanto_shorts_drama",
            "language": "Filipino/Taglish",
            "accent": "Filipino",
            "visual_style": "cinematic_realistic_filipino_drama",
        }
        return self.production_state["project"]

    def _gate_configure(self) -> bool:
        """Lightweight config validation."""
        cfg = self.production_state["project"]
        if not cfg.get("topic"):
            logger.error("Configure gate: no topic set")
            return False
        return True

    # ------------------------------------------------------------------
    # Story
    # ------------------------------------------------------------------

    def _do_story(self) -> StoryDoc:
        """Generate story using the story engine."""
        story = self.story_engine.generate_story(
            topic=self.topic,
            niche="pinoy_drama",
            target_seconds=self.target_seconds,
        )
        self.story = story
        self.production_state["story"] = {
            "title": story.title,
            "logline": story.logline,
            "niche": story.niche,
            "target_seconds": story.target_seconds,
            "total_scenes": story.total_scenes,
            "acts": [{"act_number": a.act_number, "title": a.title} for a in story.acts],
        }
        # Save story artifact
        story_path = self.output_dir / "story.json"
        from app.story.models import save_story
        save_story(story, story_path)
        logger.info("Story saved to %s", story_path)
        return self.production_state["story"]

    def _gate_story(self) -> bool:
        """Basic story validation."""
        if not self.story or self.story.total_scenes < 2:
            logger.error("Story gate: story has fewer than 2 scenes")
            return False
        return True

    # ------------------------------------------------------------------
    # Character Bible
    # ------------------------------------------------------------------

    def _do_character_bible(self) -> CharacterBible:
        """Generate character bible."""
        self.character_bible = self.story_engine.generate_character_bible(self.story)
        self.production_state["characters"] = {
            "count": len(self.character_bible.characters),
            "characters": [
                {
                    "name": c.name,
                    "appearance": c.appearance,
                    "clothing": c.clothing,
                    "props": c.props,
                }
                for c in self.character_bible.characters
            ],
            "notes": self.character_bible.notes,
        }
        logger.info("Character Bible: %d characters", len(self.character_bible.characters))
        return self.production_state["characters"]

    # ------------------------------------------------------------------
    # Visual Bible
    # ------------------------------------------------------------------

    def _do_visual_bible(self) -> VisualBible:
        """Generate visual bible."""
        self.visual_bible = self.story_engine.generate_visual_bible(
            self.story, self.character_bible
        )
        self.production_state["visual_bible"] = {
            "color_palette": self.visual_bible.color_palette,
            "lighting": self.visual_bible.lighting,
            "camera_style": self.visual_bible.camera_style,
            "notes": self.visual_bible.notes,
            "aspect_ratio": self.visual_bible.aspect_ratio,
        }
        logger.info("Visual Bible generated: %s", self.visual_bible.camera_style)
        return self.production_state["visual_bible"]

    # ------------------------------------------------------------------
    # Scenes
    # ------------------------------------------------------------------

    def _do_scenes(self) -> list[PlanarScene]:
        """Plan scenes from story + bibles."""
        self.planner = ScenePlanner(target_clip_seconds=self.clip_duration)
        scenes = self.planner.plan(
            self.story,
            self.character_bible,
            self.visual_bible,
            target_clip_seconds=self.clip_duration,
        )
        self.production_state["scenes"] = [
            {
                "scene_id": s.scene_id,
                "scene_number": s.scene_number,
                "title": s.title,
                "description": s.description,
                "target_clip_seconds": s.target_clip_seconds,
                "complexity": s.complexity,
            }
            for s in scenes
        ]
        logger.info("ScenePlanner: %d scenes planned", len(scenes))
        return scenes

    # ------------------------------------------------------------------
    # Complexity Optimization
    # ------------------------------------------------------------------

    def _do_complexity_optimize(self) -> list[dict[str, Any]]:
        """Run complexity optimizer on planned scenes."""
        if not self.planner or not self.story:
            return []
        self.optimizer = SceneOptimizer()
        results = []
        for scene_data in self.production_state["scenes"]:
            # Use the ScenePlanner's own complexity classifier
            from app.story.models import Scene as StoryScene
            story_scene = StoryScene(
                scene_number=scene_data["scene_number"],
                title=scene_data["title"],
                description=scene_data["description"],
            )
            complexity = self.planner.classify_complexity(story_scene)
            scene_data["complexity"] = complexity
            results.append({
                "scene_number": scene_data["scene_number"],
                "complexity": complexity,
                "recommendation": self.optimizer.recommend_action(complexity),
            })
        logger.info("Complexity optimization: %d scenes classified", len(results))
        return results

    # ------------------------------------------------------------------
    # Continuity
    # ------------------------------------------------------------------

    def _do_continuity(self) -> dict[str, Any]:
        """Build continuity state from scenes + bibles."""
        if not self.planner or not self.story or not self.character_bible:
            return {}

        continuity_state: dict[str, Any] = {
            "characters": {},
            "locations": {},
            "wardrobe": {},
            "props": {},
            "time": {},
            "weather": "daylight",
            "emotional_state": {},
            "relationships": {},
            "plot": {},
        }

        for scene in self.planner.plan(
            self.story, self.character_bible, self.visual_bible,
            target_clip_seconds=self.clip_duration,
        ):
            # Extract character presence from continuity DNA
            try:
                dna = json.loads(scene.continuity_dna)
            except (json.JSONDecodeError, TypeError):
                dna = {}

            characters = dna.get("characters", [])
            for char_data in characters:
                name = char_data.get("name", "")
                if name:
                    continuity_state["characters"][name] = {
                        "appearance": char_data.get("appearance", ""),
                        "clothing": char_data.get("clothing", ""),
                        "props": char_data.get("props", []),
                    }

        self.production_state["continuity"] = continuity_state
        logger.info("Continuity state: %d characters tracked", len(continuity_state["characters"]))
        return continuity_state

    # ------------------------------------------------------------------
    # Compile Prompts
    # ------------------------------------------------------------------

    def _do_compile_prompts(self) -> list[CompiledPrompt]:
        """Compile all scenes into provider-ready prompts."""
        if not self.planner or not self.story or not self.character_bible:
            return []

        scenes = self.planner.plan(
            self.story, self.character_bible, self.visual_bible,
            target_clip_seconds=self.clip_duration,
        )

        self.compiler = PromptCompiler(provider=self._provider_registry_key)
        compiled = self.compiler.compile_multi(
            scenes,
            story=self.story,
            character_bible=self.character_bible,
            visual_bible=self.visual_bible,
        )

        prompt_summaries = []
        for cp in compiled:
            prompt_summaries.append({
                "scene_id": cp.scene_id,
                "scene_number": cp.scene_number,
                "provider": cp.provider,
                "prompt_text": cp.prompt_text,
                "clip_seconds": cp.clip_seconds,
                "metadata": cp.metadata,
            })
            logger.info("Compiled prompt for scene %s (%d chars)",
                        cp.scene_id, len(cp.prompt_text))

        self.production_state["compiled_prompts"] = prompt_summaries
        return compiled

    # ------------------------------------------------------------------
    # Gates
    # ------------------------------------------------------------------

    def _gate_prompts(self) -> bool:
        """Validate all compiled prompts have no unresolved placeholders."""
        if not self.production_state.get("compiled_prompts"):
            logger.error("Prompt gate: no compiled prompts")
            return False

        all_clean = True
        for prompt_data in self.production_state["compiled_prompts"]:
            try:
                validate_prompt_no_placeholders(
                    prompt_data["prompt_text"],
                    prompt_data["scene_id"],
                )
            except PromptPlaceholderError as exc:
                logger.error("Prompt gate FAILED: %s", exc)
                all_clean = False

        if all_clean:
            logger.info("Prompt gate: all %d prompts pass placeholder check",
                        len(self.production_state["compiled_prompts"]))
        return all_clean

    def _gate_story_quality(self) -> bool:
        """Run story quality gate. Returns True if pass or warning-level only."""
        if not self.story:
            return False

        gate = StoryQualityGate()
        issues = gate.validate(self.story)

        errors = [i for i in issues if i["severity"] == "error"]
        warnings = [i for i in issues if i["severity"] == "warning"]

        if errors:
            logger.error("Story quality gate FAILED with %d errors:", len(errors))
            for issue in errors:
                logger.error("  [%s] %s: %s", issue["check"], issue["severity"], issue["message"])
            self.production_state["quality_issues"] = issues
            return False

        if warnings:
            logger.warning("Story quality gate: %d warnings:", len(warnings))
            for issue in warnings:
                logger.warning("  [%s] %s: %s", issue["check"], issue["severity"], issue["message"])
            self.production_state["quality_issues"] = issues

        logger.info("Story quality gate: PASS (%d warnings)", len(warnings))
        return True

    # ------------------------------------------------------------------
    # Queue Jobs
    # ------------------------------------------------------------------

    def _do_queue_jobs(self) -> list[dict[str, Any]]:
        """Queue generation jobs for all scenes."""
        if not self.compiler or not self.production_state.get("compiled_prompts"):
            return []

        self.session = get_session()
        self.queue = GenerationQueue(self.session)
        self.queue.set_provider(
            self._provider_registry_key,
            {"cdp_port": 9228, "download_dir": "~/Data/gf-downloads"},
        )
        # Authenticate provider against the live Chrome session
        self.queue.provider.authenticate({})

        # Create or get project
        project = self.session.exec(
            select(Project).where(Project.name == self.project_name)
        ).first()
        if not project:
            project = Project(
                name=self.project_name,
                niche="pinoy_drama",
                topic=self.topic,
                target_seconds=self.target_seconds,
                status=ProjectStatus.READY_TO_GENERATE,
            )
            self.session.add(project)
            self.session.commit()
            self.session.refresh(project)

        job_summaries = []
        for prompt_data in self.production_state["compiled_prompts"]:
            # Create DB prompt
            db_prompt = DBPrompt(
                scene_id="",
                provider=self._provider_registry_key,
                prompt_text=prompt_data["prompt_text"],
                compiled_metadata=json.dumps(prompt_data.get("metadata", {})),
            )
            self.session.add(db_prompt)
            self.session.commit()
            self.session.refresh(db_prompt)

            # Create DB scene
            db_scene = DBS_cene(
                project_id=project.id,
                scene_number=prompt_data["scene_number"],
                title=prompt_data.get("scene_id", f"scene-{prompt_data['scene_number']}"),
                description="",
                target_clip_seconds=prompt_data["clip_seconds"],
                complexity="LOW",
            )
            self.session.add(db_scene)
            self.session.commit()
            self.session.refresh(db_scene)

            # Update prompt with scene_id
            db_prompt.scene_id = db_scene.id
            self.session.add(db_prompt)
            self.session.commit()

            # Create GenerationJob (PENDING → will be set to READY by queue)
            from app.core.models import GenerationJob, JobState
            gb_job = GenerationJob(
                prompt_id=db_prompt.id,
                provider=self._provider_registry_key,
                state=JobState.PENDING,
            )
            self.session.add(gb_job)
            self.session.commit()
            self.session.refresh(gb_job)

            # Move to READY via queue
            self.queue.set_jobs_ready(project.id)
            self.session.refresh(gb_job)

            # Submit to provider
            job = self.queue.submit_job(gb_job.id)
            state_val = job.state.value if hasattr(job.state, "value") else str(job.state)
            job_summaries.append({
                "job_id": job.id,
                "scene_number": prompt_data["scene_number"],
                "state": state_val,
                "prompt_id": db_prompt.id,
                "scene_id": db_scene.id,
            })

        self.session.commit()
        self.production_state["generation_jobs"] = job_summaries
        logger.info("Queued %d generation jobs", len(job_summaries))
        return job_summaries

    # ------------------------------------------------------------------
    # Generate (async — caller calls this for each job)
    # ------------------------------------------------------------------

    def generate_next(self) -> dict[str, Any] | None:
        """Generate the next queued job. Returns result or None if nothing ready."""
        if not self.queue:
            return None

        # Poll queue first to update BLOCKED→READY when provider is ready
        self.queue.poll_queue()
        job = self.queue.get_next_ready_job()
        if not job:
            return None

        result = self.queue.submit_job(job.id)
        # Update job summary in production state
        for js in self.production_state["generation_jobs"]:
            if js["job_id"] == job.id:
                js["state"] = job.state.value if hasattr(job.state, "value") else str(job.state)
                break
        return {
            "job_id": job.id,
            "scene_number": job_summary["scene_number"] if (job_summary := next((js for js in self.production_state["generation_jobs"] if js.get("job_id") == job.id), None)) else 0,
            "state": job.state.value if hasattr(job.state, "value") else str(job.state),
            "success": job.state == JobState.COMPLETED if hasattr(job.state, "value") else job.state == "COMPLETED",
        }

    def poll_all(self) -> list[dict[str, Any]]:
        """Poll all submitted jobs and update state."""
        if not self.queue:
            return []

        results = []
        for job_summary in self.production_state["generation_jobs"]:
            job_id = job_summary.get("job_id")
            if not job_id:
                continue
            try:
                job = self.session.get(GenerationJob, job_id)
                if job and job.state in (JobState.SUBMITTED, JobState.GENERATING):
                    polled = self.queue.poll_job(job_id)
                    results.append({
                        "job_id": job_id,
                        "state": polled.state.value if polled else job.state.value,
                    })
            except Exception as exc:
                logger.warning("Poll failed for job %s: %s", job_id, exc)

        # Update state
        for r in results:
            for j in self.production_state["generation_jobs"]:
                if j["job_id"] == r["job_id"]:
                    j["state"] = r["state"]

        return results

    # ------------------------------------------------------------------
    # QA
    # ------------------------------------------------------------------

    def qa_all_clips(self) -> list[dict[str, Any]]:
        """Run QA on all completed clips."""
        # Import here to avoid circular
        from app.qa.engine import VideoQAEngine

        qa_engine = VideoQAEngine()
        results = []

        for job_summary in self.production_state["generation_jobs"]:
            job_id = job_summary.get("job_id")
            if not job_id:
                continue
            try:
                job = self.session.get(GenerationJob, job_id)
                if job and job.state == JobState.COMPLETED and job.download_path:
                    qa_result = qa_engine.qa_clip(job.download_path)
                    qa_result["job_id"] = job_id
                    qa_result["scene_number"] = job_summary.get("scene_number")
                    results.append(qa_result)

                    # Update job state
                    if qa_result.get("passed"):
                        job.state = JobState.VALID
                    else:
                        job.state = JobState.INVALID
                    self.session.add(job)
                    self.session.commit()

                    self.production_state["qa_results"].append(qa_result)
            except Exception as exc:
                logger.warning("QA failed for job %s: %s", job_id, exc)

        passed = sum(1 for r in results if r.get("passed"))
        logger.info("QA complete: %d/%d clips passed", passed, len(results))
        return results

    # ------------------------------------------------------------------
    # Repair
    # ------------------------------------------------------------------

    def repair_failed(self) -> list[dict[str, Any]]:
        """Repair failed clips. Only regenerates failed scenes."""
        if not self.queue:
            return []

        repaired = []
        for job_summary in self.production_state["generation_jobs"]:
            job_id = job_summary.get("job_id")
            if not job_id:
                continue
            try:
                job = self.session.get(GenerationJob, job_id)
                if job and job.state in (JobState.FAILED, JobState.INVALID):
                    # Get the prompt
                    prompt = self.session.get(DBPrompt, job.prompt_id)
                    if prompt:
                        diagnosis = self.queue.repair_engine.diagnose(
                            prompt.prompt_text,
                            error_reason=job.error_reason,
                        )
                        new_prompt_text, new_version = self.queue.repair_engine.repair_prompt(
                            prompt.id,
                            error_reason=job.error_reason,
                        )
                        job.repair_applied = diagnosis["strategy"]
                        job.state = JobState.RETRY
                        self.session.add(job)
                        self.session.commit()

                        # Re-submit
                        new_job = self.queue.submit_job(job.id)
                        repaired.append({
                            "job_id": job_id,
                            "scene_number": job_summary.get("scene_number"),
                            "strategy": diagnosis["strategy"],
                            "new_state": new_job.state.value,
                        })
                        logger.info("Repaired job %s: %s → %s",
                                    job_id, diagnosis["strategy"], new_job.state.value)
            except Exception as exc:
                logger.warning("Repair failed for job %s: %s", job_id, exc)

        self.production_state["repaired_jobs"] = repaired
        return repaired

    # ------------------------------------------------------------------
    # Assembly
    # ------------------------------------------------------------------

    def assemble(self) -> dict[str, Any]:
        """Assemble final video from completed clips."""
        from app.assembly import AssemblyConfig, AssemblyInput, VideoAssembler

        # Collect completed clip paths
        clip_paths = []
        for job_summary in self.production_state["generation_jobs"]:
            job_id = job_summary.get("job_id")
            if not job_id:
                continue
            try:
                job = self.session.get(GenerationJob, job_id)
                if job and job.state == JobState.COMPLETED and job.download_path:
                    clip_paths.append(Path(job.download_path))
            except Exception:
                pass

        if not clip_paths:
            return {"success": False, "error": "No completed clips to assemble"}

        assembler = VideoAssembler(AssemblyConfig(
            output_dir=str(self.output_dir / "final"),
            target_resolution=(1080, 1920),  # 1080p vertical
        ))

        result = assembler.assemble(AssemblyInput(clips=sorted(clip_paths)))
        self.production_state["assembly"] = {
            "success": result.success,
            "output_path": str(result.output_path) if result.output_path else None,
            "duration_seconds": result.duration_seconds,
            "file_size_bytes": result.file_size_bytes,
            "error_message": result.error_message,
        }
        logger.info("Assembly: %s", result.output_path or result.error_message)
        return self.production_state["assembly"]

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def _build_report(self, status: str = "in_progress", failed_at: str | None = None) -> dict[str, Any]:
        """Build production report."""
        report = {
            "project": self.production_state.get("project", {}),
            "status": status,
            "failed_at": failed_at,
            "story": self.production_state.get("story", {}),
            "characters": self.production_state.get("characters", {}),
            "visual_bible": self.production_state.get("visual_bible", {}),
            "scenes_count": len(self.production_state.get("scenes", [])),
            "compiled_prompts_count": len(self.production_state.get("compiled_prompts", [])),
            "jobs": self.production_state.get("generation_jobs", []),
            "qa_results": self.production_state.get("qa_results", []),
            "assembly": self.production_state.get("assembly", {}),
            "turns": self.turn_results,
        }
        if self.production_state.get("quality_issues"):
            report["quality_issues"] = self.production_state["quality_issues"]
        return report

    def export_report(self, path: str | Path | None = None) -> Path:
        """Export production report to JSON file."""
        report = self._build_report()
        out_path = Path(path or self.output_dir / "production_report.json")
        out_path.write_text(json.dumps(report, indent=2, default=str))
        logger.info("Production report exported to %s", out_path)
        return out_path
