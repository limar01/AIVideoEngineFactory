"""SQLModel definitions for all domain tables.

Source: docs/DB_SCHEMA.md §3
Maps 1:1 to the SQLite DDL in database/migrations/001_initial_schema.sql.
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional
from uuid import uuid4

from pydantic import field_validator
from sqlmodel import Field, SQLModel
from sqlalchemy import Column, String, Text, Integer, DateTime
from datetime import timezone


def _utcnow() -> datetime:
    """Return a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #

class ProjectStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    BUILDING = "BUILDING"
    READY_TO_GENERATE = "READY_TO_GENERATE"
    GENERATING = "GENERATING"
    QUOTA_WAIT = "QUOTA_WAIT"
    ASSEMBLING = "ASSEMBLING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PAUSED = "PAUSED"


class SceneStatus(str, enum.Enum):
    PLANNED = "PLANNED"
    PROMPTED = "PROMPTED"
    GENERATED = "GENERATED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class JobState(str, enum.Enum):
    PENDING = "PENDING"
    READY = "READY"
    SUBMITTED = "SUBMITTED"
    GENERATING = "GENERATING"
    COMPLETED = "COMPLETED"
    DOWNLOADING = "DOWNLOADING"
    DOWNLOADED = "DOWNLOADED"
    VALIDATING = "VALIDATING"
    VALID = "VALID"
    INVALID = "INVALID"
    FAILED = "FAILED"
    RETRY = "RETRY"
    QUOTA_WAIT = "QUOTA_WAIT"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


class AccountStatus(str, enum.Enum):
    PENDING_AUTH = "PENDING_AUTH"
    AUTHORIZED = "AUTHORIZED"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    BANNED = "BANNED"
    DISABLED = "DISABLED"


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #

class Project(SQLModel, table=True):
    """A video generation project — the top-level aggregate root."""

    __tablename__ = "project"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    name: str = Field(index=True)
    description: Optional[str] = None
    niche: str
    topic: str
    target_seconds: int = Field(index=True)
    status: ProjectStatus = Field(
        default=ProjectStatus.DRAFT,
        sa_column=Column(String(32), nullable=False, default="DRAFT")
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime, nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime, nullable=False)
    )
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    artifact_path: Optional[str] = None
    qa_report_path: Optional[str] = None
    deleted_at: Optional[datetime] = None


class Scene(SQLModel, table=True):
    """A single scene within a project's story."""

    __tablename__ = "scene"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    scene_number: int
    act_number: Optional[int] = None
    title: str
    description: str
    narration_text: Optional[str] = None
    narration_seconds: Optional[float] = None
    target_clip_seconds: float = 8.0
    complexity: Optional[str] = None  # LOW | MEDIUM | HIGH
    continuity_dna: Optional[str] = None  # JSON string (serialized dict)
    status: SceneStatus = Field(
        default=SceneStatus.PLANNED,
        sa_column=Column(String(32), nullable=False, default="PLANNED")
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime, nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime, nullable=False)
    )

    def model_post_init(self, __context) -> None:
        """Validate complexity after SQLModel field assignment."""
        v = self.complexity
        if v is not None:
            allowed = {"LOW", "MEDIUM", "HIGH"}
            if v.upper() not in allowed:
                raise ValueError(f"complexity must be one of {allowed}, got '{v}'")
            self.complexity = v.upper()


class Prompt(SQLModel, table=True):
    """A compiled prompt associated with a scene."""

    __tablename__ = "prompt"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    scene_id: str = Field(foreign_key="scene.id", index=True)
    provider: str
    prompt_text: str = Field(sa_column=Column(Text, nullable=False))
    compiled_metadata: Optional[str] = None  # JSON string
    version: int = 1
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime, nullable=False)
    )


class Account(SQLModel, table=True):
    """An authorized provider account (credentials encrypted at rest)."""

    __tablename__ = "account"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    provider: str = Field(index=True)
    label: Optional[str] = None
    credentials_encrypted: Optional[str] = None
    session_state: Optional[str] = None
    session_expires: Optional[datetime] = None
    status: AccountStatus = Field(
        default=AccountStatus.PENDING_AUTH,
        sa_column=Column(String(32), nullable=False, default="PENDING_AUTH")
    )
    last_used_at: Optional[datetime] = None
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime, nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime, nullable=False)
    )


class Quota(SQLModel, table=True):
    """Per-account quota tracking — provider limits come from here, never hard-coded."""

    __tablename__ = "quota"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    account_id: str = Field(foreign_key="account.id", index=True)
    provider: str
    daily_limit: int
    used_today: int = Field(default=0, sa_column=Column(Integer, default=0))
    remaining: int = Field(sa_column=Column(Integer, nullable=False))
    reset_time: datetime = Field(sa_column=Column(DateTime, nullable=False))
    last_check_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime, nullable=False)
    )
    last_generation: Optional[datetime] = None
    error_count: int = Field(default=0, sa_column=Column(Integer, default=0))
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime, nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime, nullable=False)
    )


class GenerationJob(SQLModel, table=True):
    """A single generation job — one per scene per provider attempt.

    Master Spec §11: all states persisted. Never regenerate a VALID clip.
    """

    __tablename__ = "generation_job"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    prompt_id: str = Field(foreign_key="prompt.id", index=True)
    account_id: Optional[str] = Field(default=None, index=True)
    provider: Optional[str] = None
    state: JobState = Field(
        default=JobState.PENDING,
        sa_column=Column(String(32), nullable=False, default="PENDING")
    )
    retry_count: int = 0
    max_retries: int = 2
    submitted_at: Optional[datetime] = None
    generating_started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    download_path: Optional[str] = None
    error_reason: Optional[str] = None
    error_code: Optional[str] = None
    repair_applied: Optional[str] = None
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime, nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime, nullable=False)
    )


class RetryAttempt(SQLModel, table=True):
    """Audit trail of each retry attempt (spec §22 — repair-over-retry)."""

    __tablename__ = "retry_attempt"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    generation_job_id: str = Field(foreign_key="generation_job.id", index=True)
    attempt_number: int
    prompt_version: int
    repair_description: Optional[str] = None
    result: Optional[str] = None  # SUCCESS | FAILED
    error_reason: Optional[str] = None
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime, nullable=False)
    )


class QAResult(SQLModel, table=True):
    """Video QA results for a generated clip (spec §21)."""

    __tablename__ = "qa_result"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    generation_job_id: str = Field(foreign_key="generation_job.id", index=True)
    clip_path: str
    duration_seconds: Optional[float] = None
    expected_min: Optional[float] = None
    expected_max: Optional[float] = None
    resolution: Optional[str] = None
    aspect_ratio: Optional[str] = None
    codec: Optional[str] = None
    has_audio: Optional[bool] = None
    file_size_bytes: Optional[int] = None
    black_frame_ratio: Optional[float] = None
    corruption_detected: bool = False
    passed: bool = False
    failure_details: Optional[str] = None  # JSON string
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime, nullable=False)
    )


class Download(SQLModel, table=True):
    """Download tracking for generation job outputs."""

    __tablename__ = "download"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    generation_job_id: str = Field(foreign_key="generation_job.id", index=True)
    url: Optional[str] = None
    local_path: str
    file_size_bytes: Optional[int] = None
    download_started: Optional[datetime] = None
    download_completed: Optional[datetime] = None
    checksum: Optional[str] = None
    status: str = Field(
        default="PENDING",
        sa_column=Column(String(32), nullable=False, default="PENDING")
    )
    error_reason: Optional[str] = None
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime, nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime, nullable=False)
    )
