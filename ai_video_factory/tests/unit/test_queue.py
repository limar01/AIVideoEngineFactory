"""Unit tests for the GenerationQueue, QuotaManager, and RepairEngine."""
import pytest
from sqlmodel import SQLModel, create_engine
from sqlmodel.orm.session import Session

from app.core.models import (
    GenerationJob,
    JobState,
    Prompt,
    Scene,
)
from app.queue.service import GenerationQueue, RepairEngine, QuotaManager


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def test_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test_queue.db'}")
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(test_engine):
    with Session(test_engine) as session:
        yield session


@pytest.fixture
def queue(session):
    q = GenerationQueue(session)
    q.set_provider("mock")
    return q


def _create_test_scene_and_prompt(session, prompt_text="A spooky scene") -> tuple[Prompt, Scene, GenerationJob]:
    """Helper: create a Scene + Prompt + GenerationJob in DB."""
    project_id = "proj-test"
    scene = Scene(
        project_id=project_id,
        scene_number=1,
        title="Test Scene",
        description="A test scene",
        target_clip_seconds=8.0,
    )
    session.add(scene)
    session.commit()
    session.refresh(scene)

    prompt = Prompt(
        scene_id=scene.id,
        provider="snapgen",
        prompt_text=prompt_text,
        version=1,
    )
    session.add(prompt)
    session.commit()
    session.refresh(prompt)

    job = GenerationJob(prompt_id=prompt.id, provider="snapgen", state=JobState.PENDING)
    session.add(job)
    session.commit()
    session.refresh(job)

    return prompt, scene, job


# --------------------------------------------------------------------------- #
# QuotaManager tests
# --------------------------------------------------------------------------- #

class TestQuotaManager:
    def test_check_returns_true_when_quota_available(self, queue: GenerationQueue) -> None:
        assert queue.quota_manager is not None
        has_quota, wait = queue.quota_manager.check()
        assert has_quota is True
        assert wait == 0

    def test_check_returns_false_when_quota_exhausted(self, session, test_engine) -> None:
        from app.queue.service import GenerationQueue, QuotaManager
        from app.providers.mock import MockVideoProvider

        # Create a provider with 0 quota limit
        provider = MockVideoProvider(quota_limit=0)
        provider.authenticate({})
        qm = QuotaManager(session, provider)

        has_quota, wait = qm.check()
        # quota_limit=0, used=0 → remaining=0 → quota exhausted
        assert has_quota is False


# --------------------------------------------------------------------------- #
# RepairEngine tests
# --------------------------------------------------------------------------- #

class TestRepairEngine:
    def test_repair_engine_creates_new_prompt_version(self, session) -> None:
        prompt = Prompt(
            id="p1",
            scene_id="s1",
            provider="snapgen",
            prompt_text="A very long and complex scene with simultaneously actions",
            version=1,
        )
        session.add(prompt)
        session.commit()

        engine = RepairEngine(session)
        new_text, new_version = engine.repair_prompt("p1")
        assert new_version == 2
        assert new_text != prompt.prompt_text
        assert "simultaneously" not in new_text or "and then" in new_text


# --------------------------------------------------------------------------- #
# GenerationQueue tests
# --------------------------------------------------------------------------- #

class TestGenerationQueue:
    def test_set_jobs_ready_transitions_pending_to_ready(self, session, queue) -> None:
        # Create a PENDING job
        _, _, job = _create_test_scene_and_prompt(session)
        # Ensure it's PENDING
        job.state = JobState.PENDING
        session.add(job)
        session.commit()

        count = queue.set_jobs_ready()
        assert count == 1

        refreshed = session.get(GenerationJob, job.id)
        assert refreshed.state == JobState.READY

    def test_set_jobs_ready_quota_wait_when_exhausted(self, session, test_engine) -> None:
        # Create a provider with 0 quota
        from app.providers.mock import MockVideoProvider
        provider = MockVideoProvider(quota_limit=0)
        provider.authenticate({})

        queue = GenerationQueue(session)
        queue.provider = provider
        queue.quota_manager = QuotaManager(session, provider)

        # Create a PENDING job
        _, _, job = _create_test_scene_and_prompt(session)
        job.state = JobState.PENDING
        session.add(job)
        session.commit()

        count = queue.set_jobs_ready()
        assert count == 0

        refreshed = session.get(GenerationJob, job.id)
        assert refreshed.state == JobState.QUOTA_WAIT

    def test_submit_job_submitted(self, session, queue) -> None:
        _, _, job = _create_test_scene_and_prompt(session)
        job.state = JobState.READY
        session.add(job)
        session.commit()

        queue.provider.authenticate({})
        queue.submit_job(job.id)

        refreshed = session.get(GenerationJob, job.id)
        assert refreshed.state == JobState.SUBMITTED

    def test_get_next_ready_job(self, session, queue) -> None:
        _, _, job1 = _create_test_scene_and_prompt(session)
        _, _, job2 = _create_test_scene_and_prompt(session)

        job1.state = JobState.PENDING
        job2.state = JobState.READY
        session.add(job1)
        session.add(job2)
        session.commit()

        next_job = queue.get_next_ready_job()
        assert next_job is not None
        assert next_job.id == job2.id

    def test_get_queue_stats(self, session, queue) -> None:
        _, _, job = _create_test_scene_and_prompt(session)
        stats = queue.get_queue_stats()

        assert JobState.PENDING.value in stats
        assert stats[JobState.PENDING.value] >= 1

    def test_get_queue_stats_for_project(self, session, queue) -> None:
        _, _, job = _create_test_scene_and_prompt(session)
        stats = queue.get_queue_stats_for_project("proj-test")
        assert stats[JobState.PENDING.value] >= 1
