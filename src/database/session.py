from typing import AsyncGenerator

from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import DeclarativeBase

from src.config import settings


# Register SQLite fallback compilation for PostgreSQL-specific types
@compiles(TSVECTOR, "sqlite")
@compiles(TSVECTOR)
def compile_tsvector_sqlite(type_, compiler, **kw):
    return "TEXT"

@compiles(Vector, "sqlite")
@compiles(Vector)
def compile_vector_sqlite(type_, compiler, **kw):
    return "TEXT"


# Primary PostgreSQL engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
)

# Fallback SQLite engine for zero-setup local dev
dev_sqlite_url = "sqlite+aiosqlite:///./evidenceguard_db_v2.db"

sqlite_engine = create_async_engine(
    dev_sqlite_url,
    echo=settings.DEBUG,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

SqliteAsyncSessionLocal = async_sessionmaker(
    bind=sqlite_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


current_session_factory = SqliteAsyncSessionLocal



async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    global current_session_factory
    async with current_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
