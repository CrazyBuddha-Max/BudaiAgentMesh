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
    """建表 + 轻量迁移 (生产环境建议改用 Alembic)."""
    from app.access import models as _access_models  # noqa: F401  确保模型已注册
    from app.access.federated import FederatedPeer  # noqa: F401  联邦对等实例
    from app.agents import models as _agent_models  # noqa: F401  确保模型已注册
    from app.agents.llm import LLMProvider  # noqa: F401  大模型提供方
    from app.feedback.feedback import TaskFeedback  # noqa: F401  反馈闭环
    from app.knowledge import models as _knowledge_models  # noqa: F401  确保模型已注册
    from app.knowledge.metrics_models import MetricDefinition  # noqa: F401  指标语义层
    from app.security.acl import ColumnPolicy  # noqa: F401  列级权限
    from app.security.audit import AuditLog  # noqa: F401  审计日志
    from app.security.lineage import LineageEdge  # noqa: F401  数据血缘
    from app.security.tenant import Tenant  # noqa: F401  多租户

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _light_migrations()


# 开发环境轻量迁移: 为存量库补齐新版本新增的列 (幂等, 生产环境用 Alembic)
_ADD_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "data_sources": [
        ("retention_days", "INTEGER"),  # M5 生命周期
        ("watermark", "VARCHAR(256)"),  # M6 增量采集水位线
        ("tenant_id", "VARCHAR(64)"),  # M6 多租户
    ],
    "agent_tasks": [("collaborators", "JSON")],  # M4 协作 Agent
    "agents": [("llm_provider_id", "INTEGER")],  # M7 绑定模型提供方
}


async def _light_migrations() -> None:
    """为存量库补齐新版本新增的列 (幂等, 表不存在则跳过)."""
    from sqlalchemy import inspect, text

    async with engine.begin() as conn:
        for table, columns in _ADD_COLUMNS.items():
            try:
                existing = {
                    c["name"]
                    for c in await conn.run_sync(lambda sync, t=table: inspect(sync).get_columns(t))
                }
            except Exception:
                continue  # 表不存在则跳过, 无需告警
            for column, dtype in columns:
                if column not in existing:
                    await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {dtype}"))
