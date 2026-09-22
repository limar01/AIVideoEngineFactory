"""SnapGen provider adapter for AI Video Factory."""

from __future__ import annotations

import inspect
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from app.providers.base.provider import (
    GenerationRequest,
    GenerationResult,
    ProviderCapabilities,
    QuotaInfo,
    VideoGenerationProvider,
)


class SnapGenVideoProvider(VideoGenerationProvider):
    """Adapter for a SnapGen-style video generation API."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        config = config or {}
        super().__init__("snapgen", config)

        self.base_url = config.get("base_url", "https://snapgen.example.com")
        self.api_key = config.get("api_key") or config.get("token")
        self.browser_timeout = int(config.get("browser_timeout", 60000))
        self.generation_timeout = int(config.get("generation_timeout", 300000))
        self.download_timeout = int(config.get("download_timeout", 120000))
        self.max_daily_generations = int(config.get("max_daily_generations", 10))
        self.clip_duration_limits = config.get("clip_duration_limits", {"min": 3, "max": 10})
        self.resolution_limits = config.get("resolution_limits", ["480p", "720p", "1080p"])
        self.supported_models = config.get("supported_models", ["veo3.1-fast", "veo3.1-quality"])
        self.concurrent_limit = int(config.get("concurrent_limit", 1))
        self._jobs: Dict[str, GenerationResult] = {}
        self._headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def _normalize_status(self, raw_status: Optional[str]) -> str:
        status_map = {
            "queued": "pending",
            "pending": "pending",
            "processing": "processing",
            "running": "processing",
            "completed": "completed",
            "success": "completed",
            "failed": "failed",
            "error": "failed",
        }
        return status_map.get((raw_status or "").lower(), "pending")

    async def authenticate(self) -> bool:
        """Authenticate with the provider. This implementation accepts a configured API key."""
        if not self.api_key:
            self._authenticated = False
            return False
        self._authenticated = True
        return True

    async def check_session(self) -> bool:
        return self._authenticated

    async def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_name="snapgen",
            supported_resolutions=self.resolution_limits,
            min_duration=int(self.clip_duration_limits.get("min", 3)),
            max_duration=int(self.clip_duration_limits.get("max", 10)),
            supported_models=self.supported_models,
            supports_negative_prompts=True,
            supports_seeds=True,
            max_concurrent_generations=self.concurrent_limit,
        )

    async def get_quota(self) -> QuotaInfo:
        return QuotaInfo(
            daily_limit=self.max_daily_generations,
            daily_used=0,
            daily_remaining=self.max_daily_generations,
            reset_time=None,
            is_exhausted=False,
            quota_type="daily",
        )

    async def submit_generation(self, request: GenerationRequest) -> GenerationResult:
        if not self._authenticated:
            return GenerationResult(
                job_id="",
                status="failed",
                error_message="Not authenticated",
            )

        payload = request.to_dict()
        payload.setdefault("model", request.model or self.supported_models[0])
        payload.setdefault("resolution", request.resolution)
        payload.setdefault("duration", request.duration)
        payload.setdefault("aspect_ratio", request.aspect_ratio)

        job_id = payload.get("job_id") or f"snap_{uuid.uuid4().hex[:12]}"
        data = await self._request("POST", "/generate", payload)
        remote_job_id = (data or {}).get("job_id") or job_id
        if str((data or {}).get("job_id") or "").startswith("snap_"):
            remote_job_id = str((data or {}).get("job_id"))
        result = GenerationResult(
            job_id=remote_job_id,
            status=self._normalize_status((data or {}).get("status", "queued")),
            video_url=(data or {}).get("video_url"),
            metadata={"request": payload, "raw_response": data or {}},
        )
        if result.is_pending():
            result.status = "pending"
        self._jobs[remote_job_id] = result
        return result

    async def get_generation_status(self, job_id: str) -> GenerationResult:
        cached = self._jobs.get(job_id)
        data = await self._request("GET", f"/jobs/{job_id}")

        if not data and cached is not None:
            return cached

        result = GenerationResult(
            job_id=job_id,
            status=self._normalize_status((data or {}).get("status", "queued")),
            video_url=(data or {}).get("video_url"),
            metadata={"raw_response": data or {}},
            error_message=(data or {}).get("error"),
        )
        self._jobs[job_id] = result
        return result

    async def download_result(self, job_id: str, download_path: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None or not job.is_completed():
            return False

        video_url = job.video_url or self._jobs.get(job_id, {}).get("metadata", {}).get("video_url")
        if not video_url:
            return False

        path = Path(download_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=self.download_timeout) as client:
            response = await client.get(video_url)
            response.raise_for_status()
            path.write_bytes(response.content)
        return path.exists() and path.stat().st_size > 0

    async def detect_error(self, result: GenerationResult) -> Optional[str]:
        if result.is_failed():
            return result.error_message or "Unknown SnapGen error"
        return None

    async def detect_quota_exhaustion(self) -> bool:
        quota = await self.get_quota()
        return quota.is_exhausted

    async def close_session(self) -> None:
        self._authenticated = False
        self._jobs.clear()

    async def _request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        if self.base_url.endswith("/"):
            url = f"{self.base_url[:-1]}{path}"
        else:
            url = f"{self.base_url}{path}"

        headers = {"Content-Type": "application/json"}
        headers.update(self._headers)

        async with httpx.AsyncClient(headers=headers, timeout=self.generation_timeout) as client:
            response = None
            if method.upper() == "POST":
                response = await client.post(url, json=payload or {}, timeout=self.generation_timeout)
            else:
                response = await client.get(url, timeout=self.generation_timeout)

            status_code = getattr(response, "status_code", 200)
            if status_code >= 400:
                return {"status": "failed", "error": f"HTTP {status_code}"}

            if hasattr(response, "json") and callable(response.json):
                try:
                    payload = response.json()
                    if inspect.isawaitable(payload):
                        payload = await payload
                    if isinstance(payload, dict):
                        return payload
                except Exception:
                    pass

            response_headers = getattr(response, "headers", {}) or {}
            content_type = str(response_headers.get("content-type") or response_headers.get("Content-Type") or "")
            if content_type.lower().startswith("application/json"):
                try:
                    payload = response.json()
                    if inspect.isawaitable(payload):
                        payload = await payload
                    if isinstance(payload, dict):
                        return payload
                except Exception:
                    pass
            if hasattr(response, "text"):
                return {"status": "completed", "video_url": response.text}
            return {"status": "completed"}


def create_snapgen_provider(config: Optional[Dict[str, Any]] = None) -> SnapGenVideoProvider:
    """Factory creation helper."""
    return SnapGenVideoProvider(config)
