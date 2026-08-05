"""异步数据库引擎与会话管理."""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """ORM 基类."""


def _engine_url() -> str:
    # 显式配置 DATABASE_URL (PostgreSQL) 时使用; 否则回退本地 SQLite
    return settings.database_url if settings.database_url else settings.sqlite_url


engine = create_async_engine(_engine_url(), echo=settings.db_echo, future=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    """建表 (生产环境建议改用 Alembic 迁移)."""
    from app.access import models as _access_models  # noqa: F401  确保模型已注册
    from app.knowledge import models as _knowledge_models  # noqa: F401  确保模型已注册

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
