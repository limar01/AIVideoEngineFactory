"""
AI Video Factory - Main FastAPI Application

Entry point for the backend API.
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_or_init_config
from app.core.db.engine import get_database


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan manager"""
    # Startup
    config = get_or_init_config()
    db = get_database()
    
    # Initialize database
    db.initialize()
    await db.create_tables()
    
    yield
    
    # Shutdown
    # Cleanup resources if needed


def create_app() -> FastAPI:
    """Create FastAPI application"""
    config = get_or_init_config()
    
    app = FastAPI(
        title=config.app.name,
        version=config.app.version,
        description="AI Video Factory - Convert high-level requests into complete video production pipelines",
        lifespan=lifespan,
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include routers
    # from app.api.routes import projects, scenes, jobs, providers, accounts
    # app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
    # app.include_router(scenes.router, prefix="/api/scenes", tags=["scenes"])
    # app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
    # app.include_router(providers.router, prefix="/api/providers", tags=["providers"])
    # app.include_router(accounts.router, prefix="/api/accounts", tags=["accounts"])
    
    @app.get("/")
    async def root():
        """Root endpoint"""
        return {
            "name": config.app.name,
            "version": config.app.version,
            "status": "running",
        }
    
    @app.get("/health")
    async def health_check():
        """Health check endpoint"""
        return {"status": "healthy"}
    
    return app


# Create application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    config = get_or_init_config()
    uvicorn.run(
        "app.main:app",
        host=config.server.host,
        port=config.server.port,
        reload=config.app.debug,
    )
