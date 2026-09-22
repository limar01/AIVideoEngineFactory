"""Project lifecycle service — create, start, pause, resume, cancel, complete.

Source: docs/DB_SCHEMA.md §3.1, docs/STATE_MACHINE.md §1.1, docs/API_SPEC.md §3.1
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from sqlmodel import select
from sqlmodel.orm.session import Session

from app.core.config import get_settings
from app.core.models import (
    GenerationJob,
    JobState,
    Project,
    ProjectStatus,
    Prompt,
    Scene,
    SceneStatus,
)
from app.story.engine import get_story_engine

logger = logging.getLogger(__name__)


class ProjectService:
    """Manages the project lifecycle: CRUD + state transitions."""

    def __init__(self, session: Session, engine=None):
        self.session = session
        self.settings = get_settings()
        self.engine = engine  # for subagent orchestration (HermesStoryEngine)

    # ------------------------------------------------------------------ #
    # CRUD
    # ------------------------------------------------------------------ #

    def create_project(
        self,
        name: str,
        niche: str,
        topic: str,
        target_seconds: int = 600,
        description: str | None = None,
    ) -> Project:
        """Create a new project in DRAFT state."""
        project = Project(
            id=str(uuid4()),
            name=name,
            description=description,
            niche=niche,
            topic=topic,
            target_seconds=target_seconds,
            status=ProjectStatus.DRAFT,
        )
        self.session.add(project)
        self.session.commit()
        self.session.refresh(project)

        # Create artifact directory
        project_dir = self._project_dir(project.id)
        project_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Created project %s (%s, %s, %ds)", project.id, niche, topic, target_seconds)
        return project

    def get_project(self, project_id: str) -> Project | None:
        """Retrieve a project by ID."""
        return self.session.exec(
            select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))
        ).first()

    def list_projects(self) -> list[Project]:
        """List all non-deleted projects."""
        return self.session.exec(
            select(Project).where(Project.deleted_at.is_(None))
        ).all() or []  # type: ignore[return-value]

    def update_project(self, project_id: str, **fields) -> Project:
        """Update project fields (name, description, etc.)."""
        project = self.get_project(project_id)
        if not project:
            raise ValueError(f"Project not found: {project_id}")
        for key, value in fields.items():
            if hasattr(project, key):
                setattr(project, key, value)
        project.updated_at = datetime.now(timezone.utc)
        self.session.add(project)
        self.session.commit()
        self.session.refresh(project)
        return project

    def delete_project(self, project_id: str) -> None:
        """Soft-delete a project."""
        project = self.get_project(project_id)
        if not project:
            raise ValueError(f"Project not found: {project_id}")
        project.deleted_at = datetime.now(timezone.utc)
        self.session.add(project)
        self.session.commit()

    # ------------------------------------------------------------------ #
    # Lifecycle: Start
    # ------------------------------------------------------------------ #

    def start_project(self, project_id: str) -> None:
        """Begin the pipeline: story → scenes → prompts → queue.

        This triggers the story engine to generate the story, character bible,
        and visual bible. Scenes are created from the story. Prompts are compiled.
        Jobs are created and queued.
        """
        project = self.get_project(project_id)
        if not project:
            raise ValueError(f"Project not found: {project_id}")

        if project.status not in (ProjectStatus.DRAFT, ProjectStatus.PAUSED):
            raise ValueError(f"Cannot start project in status {project.status}")

        # Transition to BUILDING
        project.status = ProjectStatus.BUILDING
        self.session.add(project)
        self.session.commit()

        try:
            # Step 1: Generate story via story engine
            story_engine = get_story_engine()
            story = story_engine.generate_story(
                topic=project.topic,
                niche=project.niche,
                target_seconds=project.target_seconds,
            )
            character_bible = story_engine.generate_character_bible(story)
            visual_bible = story_engine.generate_visual_bible(story, character_bible)

            # Serialize artifacts to project dir
            self._save_artifacts(project_id, story, character_bible, visual_bible)

            # Step 2: Create scenes from story
            scenes = self._create_scenes(project_id, story, character_bible, visual_bible)

            # Step 3: Create prompts for each scene
            self._create_prompts(scenes, visual_bible)

            # Step 4: Create generation jobs for each prompt
            self._create_generation_jobs(scenes)

            # Transition to READY_TO_GENERATE
            project.status = ProjectStatus.READY_TO_GENERATE
            project.started_at = datetime.now(timezone.utc)
            self.session.add(project)
            self.session.commit()

            logger.info("Project %s started — %d scenes queued", project_id, len(scenes))

        except Exception:
            project.status = ProjectStatus.FAILED
            self.session.add(project)
            self.session.commit()
            raise

    # ------------------------------------------------------------------ #
    # Lifecycle: Pause / Resume / Cancel
    # ------------------------------------------------------------------ #

    def pause_project(self, project_id: str) -> None:
        """Pause a running project."""
        project = self.get_project(project_id)
        if not project:
            raise ValueError(f"Project not found: {project_id}")
        if project.status in (ProjectStatus.COMPLETED, ProjectStatus.FAILED,
                              ProjectStatus.DRAFT, ProjectStatus.CANCELLED):
            raise ValueError(f"Cannot pause project in status {project.status}")
        project.status = ProjectStatus.PAUSED
        self.session.add(project)
        self.session.commit()
        logger.info("Project %s paused", project_id)

    def resume_project(self, project_id: str) -> None:
        """Resume a paused or QUOTA_WAIT project."""
        project = self.get_project(project_id)
        if not project:
            raise ValueError(f"Project not found: {project_id}")
        if project.status == ProjectStatus.PAUSED:
            project.status = ProjectStatus.READY_TO_GENERATE
        elif project.status == ProjectStatus.QUOTA_WAIT:
            project.status = ProjectStatus.READY_TO_GENERATE
        elif project.status == ProjectStatus.READY_TO_GENERATE:
            pass  # already ready
        else:
            raise ValueError(f"Cannot resume project in status {project.status}")
        self.session.add(project)
        self.session.commit()
        logger.info("Project %s resumed", project_id)

    def cancel_project(self, project_id: str) -> None:
        """Cancel a project (marks as CANCELLED)."""
        project = self.get_project(project_id)
        if not project:
            raise ValueError(f"Project not found: {project_id}")
        project.status = ProjectStatus.CANCELLED
        self.session.add(project)
        self.session.commit()
        logger.info("Project %s cancelled", project_id)

    def mark_completed(self, project_id: str) -> None:
        """Mark project as completed (final assembly done)."""
        project = self.get_project(project_id)
        if not project:
            raise ValueError(f"Project not found: {project_id}")
        project.status = ProjectStatus.COMPLETED
        project.completed_at = datetime.now(timezone.utc)
        project.updated_at = datetime.now(timezone.utc)
        self.session.add(project)
        self.session.commit()
        logger.info("Project %s completed", project_id)

    # ------------------------------------------------------------------ #
    # Status / stats
    # ------------------------------------------------------------------ #

    def get_project_status(self, project_id: str) -> dict:
        """Return a status summary for a project."""
        project = self.get_project(project_id)
        if not project:
            raise ValueError(f"Project not found: {project_id}")

        # Count scenes by status (JobState already imported at module level)

        jobs = self.session.exec(
            select(GenerationJob)
            .join(Prompt, GenerationJob.prompt_id == Prompt.id)
            .join(Scene, Prompt.scene_id == Scene.id)
            .where(Scene.project_id == project_id)
        ).all()

        state_counts: dict[str, int] = {}
        for job in jobs:
            state_counts[job.state.value] = state_counts.get(job.state.value, 0) + 1

        total = len(jobs)
        valid = state_counts.get(JobState.VALID.value, 0)

        return {
            "project_id": project.id,
            "name": project.name,
            "status": project.status.value,
            "total_scenes": total,
            "valid_clips": valid,
            "by_state": state_counts,
            "started_at": project.started_at.isoformat() if project.started_at else None,
            "completed_at": project.completed_at.isoformat() if project.completed_at else None,
        }

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _project_dir(self, project_id: str) -> Path:
        return get_settings().projects_dir / project_id

    def _save_artifacts(self, project_id: str, story, character_bible, visual_bible) -> None:
        """Serialize story artifacts to the project's artifact folder."""
        artifact_dir = self._project_dir(project_id) / "artifacts"
        artifact_dir.mkdir(parents=True, exist_ok=True)

        (artifact_dir / "story.json").write_text(story.model_dump_json(indent=2))
        (artifact_dir / "character_bible.json").write_text(character_bible.model_dump_json(indent=2))
        (artifact_dir / "visual_bible.json").write_text(visual_bible.model_dump_json(indent=2))

        logger.info("Saved story artifacts for project %s", project_id)

    def _create_scenes(self, project_id: str, story, character_bible, visual_bible) -> list[Scene]:
        """Create Scene rows from the StoryDoc."""
        scenes: list[Scene] = []

        # Build continuity DNA dict
        continuity = {
            "character_appearance": {c.name: c.appearance for c in character_bible.characters},
            "character_clothing": {c.name: c.clothing for c in character_bible.characters},
            "color_palette": visual_bible.color_palette,
            "lighting": visual_bible.lighting,
            "camera_style": visual_bible.camera_style,
            "aspect_ratio": visual_bible.aspect_ratio,
        }
        continuity_str = json.dumps(continuity, sort_keys=True)

        for scene in story.all_scenes:
            db_scene = Scene(
                id=str(uuid4()),
                project_id=project_id,
                scene_number=scene.scene_number,
                act_number=scene.act_number,
                title=scene.title,
                description=scene.description,
                narration_text=scene.narration_text,
                narration_seconds=scene.narration_seconds,
                target_clip_seconds=scene.target_clip_seconds,
                complexity="MEDIUM",
                continuity_dna=continuity_str,
                status=SceneStatus.PLANNED,
            )
            self.session.add(db_scene)
            scenes.append(db_scene)

        self.session.commit()
        return scenes

    def _create_prompts(self, scenes: list[Scene], visual_bible) -> None:
        """Create Prompt rows for each scene.

        The actual prompt compilation logic lives in app/prompts/compiler.py —
        this foundation method creates the DB rows with a basic compiled prompt.
        """
        for scene in scenes:
            # Basic prompt: narration + visual bible guidance + continuity DNA
            parts = [
                f"Video prompt for a {visual_bible.lighting} scene.",
                f"Style: {visual_bible.camera_style}.",
                f"Colors: {', '.join(visual_bible.color_palette) if visual_bible.color_palette else 'default'}.",
                f"Scene: {scene.description}",
                f"Narration: {scene.narration_text or 'silent'}",
                f"Duration: {scene.target_clip_seconds}s",
                f"Aspect ratio: {visual_bible.aspect_ratio or '16:9'}",
            ]
            prompt_text = " ".join(p for p in parts if p)

            prompt = Prompt(
                id=str(uuid4()),
                scene_id=scene.id,
                provider="snapgen",
                prompt_text=prompt_text,
                compiled_metadata=json.dumps({
                    "scene_number": scene.scene_number,
                    "continuity_dna": scene.continuity_dna,
                    "target_seconds": scene.target_clip_seconds,
                }, sort_keys=True),
                version=1,
            )
            self.session.add(prompt)

        self.session.commit()

    def _create_generation_jobs(self, scenes: list[Scene]) -> None:
        """Create a GenerationJob for each scene's latest prompt."""
        for scene in scenes:
            # Get the latest prompt for this scene
            prompt = self.session.exec(
                select(Prompt).where(Prompt.scene_id == scene.id)
                .order_by(Prompt.created_at.desc())
                .limit(1)
            ).first()

            if not prompt:
                continue

            job = GenerationJob(
                id=str(uuid4()),
                prompt_id=prompt.id,
                provider=prompt.provider,
                state=JobState.PENDING,
                max_retries=2,
            )
            self.session.add(job)

        self.session.commit()
        logger.info("Created %d generation jobs", len(scenes))
