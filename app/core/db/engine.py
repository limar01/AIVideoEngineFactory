"""
AI Video Factory - Database Engine

Database connection and session management.
"""
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker

from app.core.config import get_or_init_config
from app.core.db.models import Base


class DatabaseEngine:
    """Database engine manager"""
    
    def __init__(self):
        self.engine = None
        self.async_session_maker = None
        self._initialized = False
    
    def initialize(self):
        """Initialize database engine"""
        if self._initialized:
            return
        
        config = get_or_init_config()
        
        # Create async engine
        self.engine = create_async_engine(
            config.database.url,
            echo=config.database.echo,
            future=True,
        )
        
        # Create session maker
        self.async_session_maker = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
        
        self._initialized = True
    
    async def create_tables(self):
        """Create all database tables"""
        if not self._initialized:
            self.initialize()
        
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    
    async def drop_tables(self):
        """Drop all database tables (for testing)"""
        if not self._initialized:
            self.initialize()
        
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get database session"""
        if not self._initialized:
            self.initialize()
        
        async with self.async_session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()


# Global database instance
_db = DatabaseEngine()


def get_database() -> DatabaseEngine:
    """Get database instance"""
    return _db


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting database sessions"""
    db = get_database()
    async for session in db.get_session():
        yield session
