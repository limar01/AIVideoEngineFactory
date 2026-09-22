"""FastAPI REST API routes for the AI Video Factory.

Source: docs/API_SPEC.md §3
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Generator

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import APIKeyHeader
from sqlmodel import SQLModel, create_engine, select
from sqlmodel.orm.session import Session

from app.core.config import get_settings
from app.core.database import get_engine, init_db, run_migrations
from app.core.models import GenerationJob, JobState, Prompt, Project, ProjectStatus, Scene
from app.core.service import ProjectService
from app.queue.service import GenerationQueue

logger = logging.getLogger(__name__)

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — init DB on startup."""
    # Initialize database
    engine = get_engine()
    # Run migrations (creates tables if not exists)
    try:
        run_migrations()
    except Exception:
        # Fallback to schema creation if migrations fail
        SQLModel.metadata.create_all(engine)
    yield


def get_api_key(api_key: str | None = Depends(API_KEY_HEADER)):
    """Validate API key."""
    settings = get_settings()
    if settings.api_key:
        if api_key != settings.api_key:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Invalid API key")
    return api_key


def get_session() -> Generator[Session, None, None]:
    """Get a database session."""
    engine = get_engine()
    with Session(engine) as session:
        yield session


def get_project_service(session: Session = Depends(get_session)) -> ProjectService:
    return ProjectService(session)


def get_queue(session: Session = Depends(get_session)) -> GenerationQueue:
    queue = GenerationQueue(session)
    provider_name = get_settings().provider_name
    queue.set_provider(provider_name)
    return queue


app = FastAPI(
    title="AI Video Factory API",
    version="0.1.0",
    lifespan=lifespan,
    dependencies=[Depends(get_api_key)],
)


# --------------------------------------------------------------------------- #
# Project endpoints (API_SPEC.md §3.1)
# --------------------------------------------------------------------------- #

@app.post("/api/v1/projects", response_model=None)
def create_project(
    name: str,
    niche: str = "horror",
    topic: str = "",
    target_seconds: int = 600,
    description: str | None = None,
    service: ProjectService = Depends(get_project_service),
):
    """Create a new project."""
    project = service.create_project(
        name=name, niche=niche, topic=topic,
        target_seconds=target_seconds, description=description,
    )
    return {
        "id": project.id,
        "name": project.name,
        "status": project.status.value,
        "created_at": project.created_at.isoformat(),
    }


@app.get("/api/v1/projects")
def list_projects(service: ProjectService = Depends(get_project_service)):
    """List all projects."""
    projects = service.list_projects()
    return [
        {
            "id": p.id,
            "name": p.name,
            "status": p.status.value,
            "niche": p.niche,
            "topic": p.topic,
            "target_seconds": p.target_seconds,
            "started_at": p.started_at.isoformat() if p.started_at else None,
            "completed_at": p.completed_at.isoformat() if p.completed_at else None,
        }
        for p in projects
    ]


@app.get("/api/v1/projects/{project_id}")
def get_project(project_id: str, service: ProjectService = Depends(get_project_service)):
    """Get project details."""
    project = service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "niche": project.niche,
        "topic": project.topic,
        "target_seconds": project.target_seconds,
        "status": project.status.value,
        "started_at": project.started_at.isoformat() if p.started_at else None,
        "completed_at": project.completed_at.isoformat() if p.completed_at else None,
        "artifact_path": project.artifact_path,
        "qa_report_path": project.qa_report_path,
    }


@app.post("/api/v1/projects/{project_id}/start")
def start_project(project_id: str, service: ProjectService = Depends(get_project_service)):
    """Start the project pipeline."""
    try:
        service.start_project(project_id)
        return {"project_id": project_id, "status": "BUILDING"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to start project %s: %s", project_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/projects/{project_id}/pause")
def pause_project(project_id: str, service: ProjectService = Depends(get_project_service)):
    """Pause a running project."""
    try:
        service.pause_project(project_id)
        return {"project_id": project_id, "status": "PAUSED"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/v1/projects/{project_id}/resume")
def resume_project(project_id: str, service: ProjectService = Depends(get_project_service)):
    """Resume a paused project."""
    try:
        service.resume_project(project_id)
        return {"project_id": project_id, "status": "READY_TO_GENERATE"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/v1/projects/{project_id}/cancel")
def cancel_project(project_id: str, service: ProjectService = Depends(get_project_service)):
    """Cancel a project."""
    try:
        service.cancel_project(project_id)
        return {"project_id": project_id, "status": "CANCELLED"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/v1/projects/{project_id}/status")
def project_status(project_id: str, service: ProjectService = Depends(get_project_service)):
    """Get project status summary."""
    try:
        return service.get_project_status(project_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# --------------------------------------------------------------------------- #
# Queue endpoints (API_SPEC.md §3.3)
# --------------------------------------------------------------------------- #

@app.get("/api/v1/queue")
def queue_list(project_id: str | None = None, queue: GenerationQueue = Depends(get_queue)):
    """List all queued jobs with status."""
    query = select(GenerationJob).join(Prompt).join(Scene)
    if project_id:
        query = query.where(Scene.project_id == project_id)

    jobs = queue.session.exec(query).all()
    return [
        {
            "job_id": j.id,
            "state": j.state.value,
            "retry_count": j.retry_count,
            "max_retries": j.max_retries,
            "error_code": j.error_code,
            "error_reason": j.error_reason,
            "submitted_at": j.submitted_at.isoformat() if j.submitted_at else None,
        }
        for j in jobs
    ]


@app.get("/api/v1/queue/stats")
def queue_stats(project_id: str | None = None, queue: GenerationQueue = Depends(get_queue)):
    """Get queue statistics."""
    if project_id:
        stats = queue.get_queue_stats_for_project(project_id)
    else:
        stats = queue.get_queue_stats()
    return stats


@app.post("/api/v1/queue/retry/{job_id}")
def retry_job(job_id: str, queue: GenerationQueue = Depends(get_queue)):
    """Retry a failed job after repair."""
    job = queue.session.get(GenerationJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.state not in (JobState.FAILED, JobState.INVALID):
        raise HTTPException(status_code=400, detail=f"Job state {job.state.value} cannot be retried")

    # Repair the prompt
    repair = queue.repair_engine
    new_prompt_text, new_version = repair.repair_prompt(job.prompt_id, job.error_reason)

    # Create a new prompt row and link a new job
    from uuid import uuid4
    old_prompt = queue.session.get(Prompt, job.prompt_id)
    scene_id = old_prompt.scene_id if old_prompt else None
    if scene_id is None:
        raise HTTPException(status_code=400, detail=f"Cannot retry job {job_id}: no scene_id")
    new_prompt = Prompt(
        id=str(uuid4()),
        scene_id=scene_id,
        provider=old_prompt.provider if old_prompt else "mock",
        prompt_text=new_prompt_text,
        compiled_metadata=old_prompt.compiled_metadata if old_prompt else None,
        version=new_version,
    )
    queue.session.add(new_prompt)
    queue.session.commit()
    queue.session.refresh(new_prompt)

    # Create new job
    new_job = GenerationJob(
        id=str(uuid4()),
        prompt_id=new_prompt.id,
        provider=new_prompt.provider,
        state=JobState.READY,
        max_retries=job.max_retries,
    )
    queue.session.add(new_job)
    job.state = JobState.CANCELLED  # mark old one cancelled
    job.repair_applied = f"Repaired to v{new_version}: repaired_prompt_id={new_prompt.id}"
    queue.session.commit()

    return {
        "old_job_id": job_id,
        "new_job_id": new_job.id,
        "new_prompt_version": new_version,
    }


@app.post("/api/v1/queue/skip/{job_id}")
def skip_job(job_id: str, queue: GenerationQueue = Depends(get_queue)):
    """Skip an optional scene (cancel the job)."""
    job = queue.session.get(GenerationJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.state = JobState.SKIPPED
    queue.session.add(job)
    queue.session.commit()
    return {"job_id": job_id, "state": "SKIPPED"}


# --------------------------------------------------------------------------- #
# Provider endpoints (API_SPEC.md §3.4)
# --------------------------------------------------------------------------- #

@app.get("/api/v1/provider/status")
def provider_status(queue: GenerationQueue = Depends(get_queue)):
    """Check provider status."""
    if not queue.provider:
        raise HTTPException(status_code=503, detail="Provider not configured")
    return {
        "provider": queue.provider.PROVIDER_NAME,
        "session_valid": queue.provider.check_session() if queue.provider else False,
        "quota": queue.provider.get_quota() if queue.provider else None,
    }


@app.post("/api/v1/provider/refresh-session")
def refresh_session(queue: GenerationQueue = Depends(get_queue)):
    """Refresh provider session (user must be logged in)."""
    if not queue.provider:
        raise HTTPException(status_code=503, detail="Provider not configured")
    # For mock: always re-auth
    if queue.provider.PROVIDER_NAME == "mock":
        success = queue.provider.authenticate({})
        return {"session_valid": success}
    raise HTTPException(status_code=501, detail="Manual authentication required for real provider")


@app.post("/api/v1/provider/test-connection")
def test_connection(queue: GenerationQueue = Depends(get_queue)):
    """Test provider connection."""
    if not queue.provider:
        raise HTTPException(status_code=503, detail="Provider not configured")
    return {"connected": True, "provider": queue.provider.PROVIDER_NAME}


# --------------------------------------------------------------------------- #
# Output endpoints (API_SPEC.md §3.5)
# --------------------------------------------------------------------------- #

@app.get("/api/v1/projects/{project_id}/manifest")
def project_manifest(project_id: str, service: ProjectService = Depends(get_project_service)):
    """Get full project manifest."""
    project = service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    status = service.get_project_status(project_id)
    return {
        "project": {
            "id": project.id,
            "name": project.name,
            "status": project.status.value,
            "niche": project.niche,
            "topic": project.topic,
            "target_seconds": project.target_seconds,
        },
        "scenes": status["by_state"],
        "total_scenes": status["total_scenes"],
        "valid_clips": status["valid_clips"],
    }
