"""CLI entry point — run the API server.

Usage:
    aivf serve                     # Start the API server
    aivf init                      # Initialize config + database
"""
from __future__ import annotations

import logging
import sys

from app.api import app
from app.core.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def serve():
    """Start the FastAPI server."""
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "app.api:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.environment == "development",
        log_level=settings.log_level.lower(),
    )


def main():
    """CLI main entry point — dispatches to subcommands."""
    if len(sys.argv) < 2:
        print("AI Video Factory — use: aivf serve | init | --help")
        print("Or: python -m app.api.routes (to start server)")
        return

    cmd = sys.argv[1]
    if cmd == "serve":
        serve()
    elif cmd == "init":
        init_project()
    else:
        print(f"Unknown command: {cmd}")
        print("Available: serve, init")


def init_project():
    """Initialize config files and database."""
    from app.core.database import get_engine, init_db, run_migrations
    from app.core.config import ensure_encryption_key  # type: ignore

    # Bootstrap encryption key
    try:
        from app.core.security import ensure_encryption_key
        ensure_encryption_key()
        print("Encryption key configured.")
    except Exception as e:
        print(f"Warning: encryption key setup: {e}")
