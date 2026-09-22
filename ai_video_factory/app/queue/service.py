"""Generation queue service — schedules, dispatches, and tracks generation jobs.

Source: docs/ARCHITECTURE.md §4 (Layer 3 Quota Manager, §6 Retry/Repair)
        docs/STATE_MACHINE.md §2 (state transitions)
        docs/DB_SCHEMA.md §3.6 (GenerationJob)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from sqlmodel import func, select
from sqlmodel.orm.session import Session

from app.core.config import get_config
from app.core.models import (
    GenerationJob,
    JobState,
    Prompt,
    Scene,
)
from app.providers.base import GenerationStatus, VideoGenerationProvider
from app.providers.registry import create_provider

logger = logging.getLogger(__name__)


class QuotaManager:
    """Checks and manages provider quota.

    Provider limits come from the provider's get_quota() — never hard-coded.
    Falls back to config/quota.yaml::policy::fallback_daily_limit if the
    provider doesn't expose quota data.
    """

    def __init__(self, session: Session, provider: VideoGenerationProvider):
        self.session = session
        self.provider = provider

    def check(self) -> tuple[bool, int]:
        """Check if there's quota available.

        Returns: (has_quota: bool, estimated_wait_seconds: int)
        """
        quota_info = self.provider.get_quota()

        if quota_info.remaining is not None:
            if quota_info.remaining > 0:
                return (True, 0)
            else:
                if quota_info.reset_time:
                    try:
                        reset_dt = datetime.fromisoformat(quota_info.reset_time)
                        wait_seconds = int((reset_dt - datetime.now(timezone.utc)).total_seconds())
                        return (False, max(0, wait_seconds))
                    except (ValueError, TypeError):
                        pass
                return (False, 3600)

        # Provider doesn't expose quota — use fallback from config
        fallback = get_config("quota", "policy.fallback_daily_limit", 5)
        if fallback > 0:
            return (True, 0)
        return (False, 3600)

    def record_generation(self) -> None:
        """Record that a generation was used."""
        pass


class RepairEngine:
    """Diagnoses and repairs failed generation prompts.

    Master Spec §22: Never blindly repeat the same generation.
    """

    def __init__(self, session: Session):
        self.session = session

    def diagnose(self, prompt_text: str, error_reason: str | None = None,
                 qa_failure: dict | None = None) -> dict:
        """Analyze a failed generation and determine the repair strategy."""
        import re

        diagnosis = {
            "strategy": "simplify_action",
            "changes": [],
            "new_prompt": prompt_text,
        }

        if error_reason and "continuity" in error_reason.lower():
            diagnosis["strategy"] = "fix_continuity"
        elif error_reason and "length" in error_reason.lower():
            diagnosis["strategy"] = "shorten_prompt"
        elif error_reason and "conflict" in error_reason.lower():
            diagnosis["strategy"] = "remove_conflicts"

        new_prompt = prompt_text
        changes = []

        if diagnosis["strategy"] == "shorten_prompt":
            new_prompt = re.sub(r'(?:,?\s*"[^"]*")', '', prompt_text)
            new_prompt = re.sub(r'\s+', ' ', new_prompt).strip()
            changes.append("Trimmed optional descriptive phrases")

        elif diagnosis["strategy"] == "simplify_action":
            replacements = {"simultaneously": "and then", "while": "and", "as": "and"}
            for old, new in replacements.items():
                if old in new_prompt.lower():
                    new_prompt = new_prompt.replace(old, new)
                    changes.append(f"Replaced '{old}' with '{new}'")

        elif diagnosis["strategy"] == "reduce_characters":
            new_prompt = new_prompt.replace("multiple characters", "one character")
            changes.append("Reduced to single character focus")

        elif diagnosis["strategy"] == "fix_continuity":
            new_prompt += " [continuity: maintain consistent character appearance and clothing]"
            changes.append("Added continuity reminder")

        elif diagnosis["strategy"] == "remove_conflicts":
            new_prompt = re.sub(r'(?:,?\s*"[^"]*")', '', new_prompt)
            changes.append("Removed quoted instruction blocks")

        diagnosis["new_prompt"] = new_prompt
        diagnosis["changes"] = changes
        return diagnosis

    def repair_prompt(self, prompt_id: str, error_reason: str | None = None,
                      qa_failure: dict | None = None) -> tuple[str, int]:
        """Repair a failed prompt and return the new prompt text + new version."""
        prompt = self.session.get(Prompt, prompt_id)
        if not prompt:
            raise ValueError(f"Prompt not found: {prompt_id}")

        diagnosis = self.diagnose(prompt.prompt_text, error_reason, qa_failure)
        new_version = prompt.version + 1

        new_prompt = Prompt(
            id=str(uuid4()),
            scene_id=prompt.scene_id,
            provider=prompt.provider,
            prompt_text=diagnosis["new_prompt"],
            compiled_metadata=prompt.compiled_metadata,
            version=new_version,
        )
        self.session.add(new_prompt)
        self.session.commit()
        self.session.refresh(new_prompt)

        logger.info("Repaired prompt %s (strategy=%s, version=%d)",
                     prompt_id, diagnosis["strategy"], new_version)
        return (diagnosis["new_prompt"], new_version)


class GenerationQueue:
    """Manages the generation job queue and orchestration."""

    def __init__(self, session: Session):
        self.session = session
        self.provider: VideoGenerationProvider | None = None
        self.quota_manager: QuotaManager | None = None
        self.repair_engine = RepairEngine(session)

    def set_provider(self, provider_name: str) -> None:
        """Set the active provider (e.g. 'mock' or 'snapgen')."""
        config = get_config("providers", f"{provider_name}") or {}
        self.provider = create_provider(provider_name, config)
        self.quota_manager = QuotaManager(self.session, self.provider)

    def get_next_ready_job(self) -> GenerationJob | None:
        """Get the next job in READY state."""
        return self.session.exec(
            select(GenerationJob)
            .where(GenerationJob.state == JobState.READY)
            .order_by(GenerationJob.created_at)
        ).first()

    def set_jobs_ready(self, project_id: str | None = None) -> int:
        """Transition PENDING jobs to READY if quota is available."""
        if not self.quota_manager:
            return 0

        has_quota, wait_seconds = self.quota_manager.check()
        if not has_quota:
            jobs = self.session.exec(
                select(GenerationJob).where(
                    GenerationJob.state == JobState.PENDING
                )
            ).all()
            for job in jobs:
                job.state = JobState.QUOTA_WAIT
            self.session.commit()
            logger.info("Quota exhausted — %d jobs set to QUOTA_WAIT", len(jobs))
            return 0

        query = select(GenerationJob).where(GenerationJob.state == JobState.PENDING)
        if project_id:
            query = (
                query
                .join(Prompt)
                .join(Scene)
                .where(Scene.project_id == project_id)
            )

        jobs = self.session.exec(query).all()
        for job in jobs:
            job.state = JobState.READY
        self.session.commit()
        return len(jobs)

    def submit_job(self, job_id: str) -> GenerationJob:
        """Submit a generation job to the provider."""
        job = self.session.get(GenerationJob, job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        if job.state != JobState.READY:
            raise ValueError(f"Job {job_id} is not READY (state={job.state})")

        if not self.quota_manager or not self.provider:
            raise RuntimeError("Provider not set — call set_provider() first")

        # Check quota again
        has_quota, wait_seconds = self.quota_manager.check()
        if not has_quota:
            job.state = JobState.QUOTA_WAIT
            self.session.add(job)
            self.session.commit()
            return job

        # Get the prompt
        prompt = self.session.get(Prompt, job.prompt_id)
        if not prompt:
            raise ValueError(f"Prompt not found for job {job_id}")

        # Load scene metadata
        scene = self.session.get(Scene, prompt.scene_id)
        scene_metadata = {}
        if scene:
            try:
                scene_metadata = {
                    "scene_number": scene.scene_number,
                    "target_clip_seconds": scene.target_clip_seconds,
                    "narration_text": scene.narration_text,
                    "continuity_dna": json.loads(scene.continuity_dna) if scene.continuity_dna else {},
                }
            except (json.JSONDecodeError, TypeError):
                pass

        # Authenticate if needed
        if not self.provider.check_session():
            job.state = JobState.BLOCKED
            job.error_reason = "Provider session expired — user re-authentication required"
            self.session.add(job)
            self.session.commit()
            return job

        # Submit to provider
        result = self.provider.submit_generation(
            prompt=prompt.prompt_text,
            scene_metadata=scene_metadata,
        )

        if not result.success:
            if result.error_code and "quota" in result.error_code.lower():
                job.state = JobState.QUOTA_WAIT
            else:
                job.state = JobState.FAILED
            job.error_code = result.error_code
            job.error_reason = result.error_message
            self.session.add(job)
            self.session.commit()
            return job

        if self.provider.detect_quota_exhaustion(result.download_url or ""):
            job.state = JobState.QUOTA_WAIT
            self.session.add(job)
            self.session.commit()
            return job

        # Store result_id for polling — use error_code field temporarily
        # (in full impl this would be a separate pending_generations table)
        job.state = JobState.SUBMITTED
        job.submitted_at = datetime.now(timezone.utc)
        job.error_code = result.result_id  # type: ignore[assignment] — temporary store
        self.session.add(job)
        self.session.commit()

        logger.info("Job %s submitted to %s", job_id, self.provider.PROVIDER_NAME)
        return job

    def poll_job(self, job_id: str) -> GenerationJob:
        """Poll a running job and update its state."""
        job = self.session.get(GenerationJob, job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        if job.state not in (JobState.SUBMITTED, JobState.GENERATING):
            return job

        # result_id stored in error_code field (temporary)
        result_id = job.error_code  # type: ignore[assignment]
        if not result_id:
            job.state = JobState.FAILED
            job.error_reason = "No result_id available for polling"
            self.session.add(job)
            self.session.commit()
            return job

        if not self.provider:
            raise RuntimeError("Provider not set")

        status = self.provider.get_generation_status(result_id)

        if status == GenerationStatus.COMPLETED:
            job.state = JobState.COMPLETED
            job.completed_at = datetime.now(timezone.utc)
            job.error_code = None  # clear temporary result_id
        elif status == GenerationStatus.FAILED:
            job.state = JobState.FAILED
            job.error_reason = f"Provider returned FAILED status for {result_id}"
            job.error_code = None
        elif status == GenerationStatus.GENERATING:
            job.state = JobState.GENERATING
            if not job.generating_started_at:
                job.generating_started_at = datetime.now(timezone.utc)
        else:
            job.state = JobState.SUBMITTED

        # Timeout check
        if job.generating_started_at:
            elapsed = datetime.now(timezone.utc) - job.generating_started_at
            if elapsed > timedelta(minutes=30):
                job.state = JobState.FAILED
                job.error_reason = f"Generation timed out after {int(elapsed.total_seconds())}s"

        self.session.add(job)
        self.session.commit()
        return job

    def get_queue_stats(self) -> dict[str, int]:
        """Return counts of jobs by state."""
        result = self.session.exec(
            select(GenerationJob.state, func.count()).group_by(GenerationJob.state)
        ).all()
        counts: dict[str, int] = {}
        for state, count in result:
            state_str = state.value if hasattr(state, 'value') else str(state)
            counts[state_str] = count
        for state in JobState:
            counts.setdefault(state.value, 0)
        return counts

    def get_queue_stats_for_project(self, project_id: str) -> dict[str, int]:
        """Return counts of jobs by state for a specific project."""
        result = self.session.exec(
            select(GenerationJob.state, func.count())
            .join(Prompt)
            .join(Scene)
            .where(Scene.project_id == project_id)
            .group_by(GenerationJob.state)
        ).all()
        counts: dict[str, int] = {}
        for state, count in result:
            state_str = state.value if hasattr(state, 'value') else str(state)
            counts[state_str] = count
        for state in JobState:
            counts.setdefault(state.value, 0)
        return counts
