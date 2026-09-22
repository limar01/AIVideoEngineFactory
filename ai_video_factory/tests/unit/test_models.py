"""Unit tests for SQLModel DB models, database setup, and ProjectService."""
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlmodel import SQLModel, select, create_engine
from sqlmodel.orm.session import Session

from app.core.config import reload_settings
from app.core.database import get_engine, init_db, run_migrations
from app.core.models import (
    Account,
    AccountStatus,
    GenerationJob,
    JobState,
    Project,
    ProjectStatus,
    Prompt,
    RetryAttempt,
    Scene,
    SceneStatus,
    QAResult,
    Download,
    Quota,
)
from app.core.service import ProjectService


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def test_db(tmp_path):
    """Create a fresh test database for each test."""
    db_path = tmp_path / "test_factory.db"
    engine = create_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(test_db) -> Session:
    with Session(test_db) as session:
        yield session


@pytest.fixture
def service(session) -> ProjectService:
    return ProjectService(session)


# --------------------------------------------------------------------------- #
# Model tests
# --------------------------------------------------------------------------- #

class TestProjectModel:
    def test_create_project(self, session: Session) -> None:
        project = Project(
            id="test-123",
            name="Test Horror",
            niche="horror",
            topic="haunted doll",
            target_seconds=600,
        )
        session.add(project)
        session.commit()
        session.refresh(project)

        assert project.id == "test-123"
        assert project.name == "Test Horror"
        assert project.status == ProjectStatus.DRAFT
        assert project.target_seconds == 600

    def test_project_default_status(self) -> None:
        p = Project(id="x", name="T", niche="n", topic="t", target_seconds=10)
        assert p.status == ProjectStatus.DRAFT

    def test_project_soft_delete(self, session: Session) -> None:
        p = Project(id="x", name="T", niche="n", topic="t", target_seconds=10)
        session.add(p)
        session.commit()

        p.deleted_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        session.add(p)
        session.commit()

        # Should not find deleted project
        result = session.exec(select(Project).where(Project.id == "x")).first()
        assert result is not None
        assert result.deleted_at is not None


class TestSceneModel:
    def test_scene_defaults(self, session: Session) -> None:
        scene = Scene(
            project_id="proj-1",
            scene_number=1,
            title="Opening",
            description="Something happens",
        )
        session.add(scene)
        session.commit()
        session.refresh(scene)

        assert scene.target_clip_seconds == 8.0
        assert scene.status == SceneStatus.PLANNED
        assert scene.complexity is None
        assert scene.continuity_dna is None

    def test_scene_complexity_validation(self) -> None:
        # LOW/MEDIUM/HIGH should work
        s = Scene(scene_number=1, title="T", description="D", complexity="LOW")
        assert s.complexity == "LOW"

        with pytest.raises(Exception):
            Scene(scene_number=1, title="T", description="D", complexity="INVALID")


class TestPromptModel:
    def test_prompt_version_defaults_to_1(self, session: Session) -> None:
        prompt = Prompt(
            scene_id="scene-1",
            provider="snapgen",
            prompt_text="A spooky scene",
        )
        session.add(prompt)
        session.commit()
        session.refresh(prompt)

        assert prompt.version == 1
        assert prompt.provider == "snapgen"


class TestGenerationJobModel:
    def test_job_defaults(self, session: Session) -> None:
        job = GenerationJob(prompt_id="prompt-1")
        session.add(job)
        session.commit()
        session.refresh(job)

        assert job.state == JobState.PENDING
        assert job.retry_count == 0
        assert job.max_retries == 2

    def test_job_state_transitions(self, session: Session) -> None:
        job = GenerationJob(prompt_id="prompt-1")
        session.add(job)
        session.commit()
        session.refresh(job)

        job.state = JobState.SUBMITTED
        session.add(job)
        session.commit()

        assert job.state == JobState.SUBMITTED


class TestAccountModel:
    def test_account_defaults(self, session: Session) -> None:
        acct = Account(provider="snapgen", label="My Account")
        session.add(acct)
        session.commit()
        session.refresh(acct)

        assert acct.status == AccountStatus.PENDING_AUTH
        assert acct.credentials_encrypted is None

    def test_account_store_encrypted_credentials(self, session: Session) -> None:
        acct = Account(
            provider="snapgen",
            label="Test",
            credentials_encrypted="encrypted_blob_here",
        )
        session.add(acct)
        session.commit()
        session.refresh(acct)

        assert acct.credentials_encrypted == "encrypted_blob_here"


class TestQuotaModel:
    def test_quota_initial_values(self, session: Session) -> None:
        quota = Quota(
            account_id="acct-1",
            provider="snapgen",
            daily_limit=10,
            remaining=10,
            reset_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        session.add(quota)
        session.commit()
        session.refresh(quota)

        assert quota.used_today == 0
        assert quota.remaining == 10
        assert quota.error_count == 0


# --------------------------------------------------------------------------- #
# Database module tests
# --------------------------------------------------------------------------- #

class TestDatabase:
    def test_run_migrations_creates_tables(self, tmp_path) -> None:
        # Verify the migrations system is importable and functional
        from app.core.database import run_migrations, init_db
        assert callable(run_migrations)
        assert callable(init_db)

        # Verify migration SQL file exists
        migrations_dir = Path(__file__).parent.parent.parent / "database" / "migrations"
        sql_files = list(migrations_dir.glob("*.sql"))
        assert len(sql_files) > 0, "Migration SQL files should exist"

    def test_engine_uses_wal_mode(self, tmp_path) -> None:
        db_path = tmp_path / "test_wal.db"
        engine = create_engine(f"sqlite:///{db_path}")
        SQLModel.metadata.create_all(engine)
        from app.core.database import _enable_wal
        _enable_wal(engine)

        with engine.connect() as conn:
            result = conn.exec_driver_sql("PRAGMA journal_mode")
            mode = [r[0] for r in result][0]
            assert mode == "wal"


# --------------------------------------------------------------------------- #
# ProjectService tests
# --------------------------------------------------------------------------- #

class TestProjectService:
    def test_create_and_retrieve_project(self, session: Session) -> None:
        svc = ProjectService(session)
        project = svc.create_project(
            name="Horror Test",
            niche="horror",
            topic="haunted mirror",
            target_seconds=300,
        )

        assert project.name == "Horror Test"
        assert project.status == ProjectStatus.DRAFT

        retrieved = svc.get_project(project.id)
        assert retrieved is not None
        assert retrieved.name == "Horror Test"

    def test_list_projects(self, session: Session) -> None:
        svc = ProjectService(session)
        svc.create_project(name="P1", niche="horror", topic="t1", target_seconds=600)
        svc.create_project(name="P2", niche="comedy", topic="t2", target_seconds=300)

        projects = svc.list_projects()
        assert len(projects) == 2

    def test_update_project(self, session: Session) -> None:
        svc = ProjectService(session)
        project = svc.create_project(name="Test", niche="horror", topic="t", target_seconds=600)
        svc.update_project(project.id, name="Updated Name")

        updated = svc.get_project(project.id)
        assert updated.name == "Updated Name"

    def test_delete_project_soft(self, session: Session) -> None:
        svc = ProjectService(session)
        project = svc.create_project(name="Test", niche="horror", topic="t", target_seconds=600)
        svc.delete_project(project.id)

        assert svc.get_project(project.id) is None
        # But it still exists in DB (soft delete)
        hard = session.exec(select(Project).where(Project.id == project.id)).first()
        assert hard is not None
        assert hard.deleted_at is not None

    def test_get_nonexistent_project_returns_none(self, session: Session) -> None:
        svc = ProjectService(session)
        assert svc.get_project("nonexistent-id") is None

    def test_update_nonexistent_raises(self, session: Session) -> None:
        svc = ProjectService(session)
        with pytest.raises(ValueError, match="not found"):
            svc.update_project("nonexistent", name="X")
