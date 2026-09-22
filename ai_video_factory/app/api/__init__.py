"""API module — FastAPI app and routes.

Source: docs/ARCHITECTURE.md §3 (Module Map), docs/API_SPEC.md
"""
from app.api.routes import app

__all__ = ["app"]
