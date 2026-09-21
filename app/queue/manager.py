"""
AI Video Factory - Generation Queue Manager

Manages the generation job queue with persistence and retry logic.
"""
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.core.db.models import (
    GenerationJob,
    JobStatus,
    Scene,
    Project,
)
from app.core.config import get_or_init_config
from app.providers.base.provider import (
    VideoGenerationProvider,
    GenerationRequest,
    GenerationResult,
)


class GenerationQueueManager:
    """
    Manages the generation job queue.
    
    Handles job submission, status tracking, retries, and quota management.
    """
    
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        self.config = get_or_init_config()
        self._running = False
        self._current_jobs: Dict[int, asyncio.Task] = {}
    
    async def create_job(
        self,
        scene_id: int,
        project_id: int,
        provider_name: str,
        account_id: Optional[int] = None,
        priority: int = 0,
    ) -> GenerationJob:
        """Create a new generation job"""
        job = GenerationJob(
            scene_id=scene_id,
            project_id=project_id,
            provider_name=provider_name,
            account_id=account_id,
            status=JobStatus.PENDING,
            priority=priority,
            max_retries=self.config.retry.max_retries,
        )
        
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        
        return job
    
    async def get_pending_jobs(
        self, 
        project_id: Optional[int] = None,
        limit: int = 10,
    ) -> List[GenerationJob]:
        """Get pending jobs ordered by priority"""
        query = select(GenerationJob).where(
            GenerationJob.status.in_([
                JobStatus.PENDING,
                JobStatus.READY,
                JobStatus.RETRY,
            ])
        )
        
        if project_id:
            query = query.where(GenerationJob.project_id == project_id)
        
        query = query.order_by(
            GenerationJob.priority.desc(),
            GenerationJob.created_at.asc(),
        ).limit(limit)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_job(self, job_id: int) -> Optional[GenerationJob]:
        """Get a specific job by ID"""
        query = select(GenerationJob).where(GenerationJob.id == job_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def get_jobs_by_status(
        self, 
        status: JobStatus,
        project_id: Optional[int] = None,
    ) -> List[GenerationJob]:
        """Get jobs by status"""
        query = select(GenerationJob).where(GenerationJob.status == status)
        
        if project_id:
            query = query.where(GenerationJob.project_id == project_id)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def update_job_status(
        self,
        job_id: int,
        status: JobStatus,
        last_error: Optional[str] = None,
        provider_job_id: Optional[str] = None,
    ):
        """Update job status"""
        now = datetime.utcnow()
        
        update_data = {
            "status": status,
            "updated_at": now,
        }
        
        if last_error:
            update_data["last_error"] = last_error
        
        if provider_job_id:
            update_data["provider_job_id"] = provider_job_id
        
        if status == JobStatus.SUBMITTED:
            update_data["submitted_at"] = now
        elif status == JobStatus.GENERATING:
            update_data["started_at"] = now
        elif status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.VALID):
            update_data["completed_at"] = now
        
        await self.db.execute(
            update(GenerationJob)
            .where(GenerationJob.id == job_id)
            .values(**update_data)
        )
        await self.db.commit()
    
    async def increment_retry(self, job_id: int) -> bool:
        """
        Increment retry count for a job.
        
        Returns True if retry is allowed, False if max retries exceeded.
        """
        job = await self.get_job(job_id)
        if not job:
            return False
        
        if job.retry_count >= job.max_retries:
            return False
        
        await self.update_job_status(
            job_id,
            JobStatus.RETRY,
        )
        
        # Update retry count
        await self.db.execute(
            update(GenerationJob)
            .where(GenerationJob.id == job_id)
            .values(retry_count=job.retry_count + 1)
        )
        await self.db.commit()
        
        return True
    
    async def mark_job_failed(
        self,
        job_id: int,
        error_message: str,
    ) -> bool:
        """
        Mark job as failed or schedule retry.
        
        Returns True if job will be retried, False if permanently failed.
        """
        job = await self.get_job(job_id)
        if not job:
            return False
        
        # Check if retry is allowed
        can_retry = (
            job.retry_count < job.max_retries and
            self._is_scene_retryable(job.scene_id)
        )
        
        if can_retry:
            await self.increment_retry(job_id)
            return True
        else:
            await self.update_job_status(
                job_id,
                JobStatus.FAILED,
                last_error=error_message,
            )
            
            # Update scene status
            await self._update_scene_status(job.scene_id, "failed", error_message)
            return False
    
    async def _is_scene_retryable(self, scene_id: int) -> bool:
        """Check if scene allows retries"""
        query = select(Scene).where(Scene.id == scene_id)
        result = await self.db.execute(query)
        scene = result.scalar_one_or_none()
        
        if not scene:
            return False
        
        # Optional scenes may be skipped after failures
        # Mandatory scenes should be retried
        return True  # For now, allow retries for all
    
    async def _update_scene_status(
        self,
        scene_id: int,
        status: str,
        error_message: Optional[str] = None,
    ):
        """Update scene generation status"""
        await self.db.execute(
            update(Scene)
            .where(Scene.id == scene_id)
            .values(
                generation_status=status,
                error_message=error_message,
                updated_at=datetime.utcnow(),
            )
        )
        await self.db.commit()
    
    async def submit_job_to_provider(
        self,
        job: GenerationJob,
        provider: VideoGenerationProvider,
        request: GenerationRequest,
    ) -> bool:
        """Submit job to provider"""
        try:
            # Validate request
            if not await provider.validate_request(request):
                await self.update_job_status(
                    job.id,
                    JobStatus.FAILED,
                    last_error="Invalid request parameters",
                )
                return False
            
            # Submit generation
            result = await provider.submit_generation(request)
            
            if result.is_failed():
                await self.update_job_status(
                    job.id,
                    JobStatus.FAILED,
                    last_error=result.error_message,
                )
                return False
            
            # Update job with provider job ID
            await self.update_job_status(
                job.id,
                JobStatus.SUBMITTED,
                provider_job_id=result.job_id,
            )
            
            return True
            
        except Exception as e:
            await self.update_job_status(
                job.id,
                JobStatus.FAILED,
                last_error=str(e),
            )
            return False
    
    async def process_completed_job(
        self,
        job: GenerationJob,
        provider: VideoGenerationProvider,
        download_path: str,
    ) -> bool:
        """Process a completed job - download and validate"""
        try:
            # Download video
            success = await provider.download_result(
                job.provider_job_id,
                download_path,
            )
            
            if not success:
                await self.mark_job_failed(
                    job.id,
                    "Download failed",
                )
                return False
            
            # Update job status
            await self.update_job_status(
                job.id,
                JobStatus.DOWNLOADED,
            )
            
            # Update scene with video path
            await self.db.execute(
                update(Scene)
                .where(Scene.id == job.scene_id)
                .values(
                    video_path=download_path,
                    generation_status="downloaded",
                    updated_at=datetime.utcnow(),
                )
            )
            await self.db.commit()
            
            return True
            
        except Exception as e:
            await self.mark_job_failed(
                job.id,
                f"Processing error: {str(e)}",
            )
            return False
    
    async def get_queue_stats(
        self,
        project_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Get queue statistics"""
        query = select(GenerationJob)
        
        if project_id:
            query = query.where(GenerationJob.project_id == project_id)
        
        result = await self.db.execute(query)
        jobs = list(result.scalars().all())
        
        stats = {
            "total": len(jobs),
            "pending": sum(1 for j in jobs if j.status == JobStatus.PENDING),
            "ready": sum(1 for j in jobs if j.status == JobStatus.READY),
            "submitted": sum(1 for j in jobs if j.status == JobStatus.SUBMITTED),
            "generating": sum(1 for j in jobs if j.status == JobStatus.GENERATING),
            "completed": sum(1 for j in jobs if j.status == JobStatus.COMPLETED),
            "downloading": sum(1 for j in jobs if j.status == JobStatus.DOWNLOADING),
            "downloaded": sum(1 for j in jobs if j.status == JobStatus.DOWNLOADED),
            "validating": sum(1 for j in jobs if j.status == JobStatus.VALIDATING),
            "valid": sum(1 for j in jobs if j.status == JobStatus.VALID),
            "failed": sum(1 for j in jobs if j.status == JobStatus.FAILED),
            "retry": sum(1 for j in jobs if j.status == JobStatus.RETRY),
            "blocked": sum(1 for j in jobs if j.status == JobStatus.BLOCKED),
            "quota_wait": sum(1 for j in jobs if j.status == JobStatus.QUOTA_WAIT),
        }
        
        return stats
    
    async def reset_failed_jobs(
        self,
        project_id: int,
        only_optional: bool = False,
    ) -> int:
        """Reset failed jobs for retry"""
        query = select(GenerationJob).where(
            GenerationJob.project_id == project_id,
            GenerationJob.status.in_([JobStatus.FAILED, JobStatus.BLOCKED]),
        )
        
        result = await self.db.execute(query)
        jobs = list(result.scalars().all())
        
        reset_count = 0
        for job in jobs:
            if only_optional:
                # Check if scene is optional
                scene_query = select(Scene).where(Scene.id == job.scene_id)
                scene_result = await self.db.execute(scene_query)
                scene = scene_result.scalar_one_or_none()
                
                if scene and scene.importance != "OPTIONAL":
                    continue
            
            await self.update_job_status(job.id, JobStatus.PENDING)
            await self.db.execute(
                update(GenerationJob)
                .where(GenerationJob.id == job.id)
                .values(retry_count=0)
            )
            reset_count += 1
        
        await self.db.commit()
        return reset_count
