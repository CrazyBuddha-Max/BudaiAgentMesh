"""审计日志: 全链路操作留痕, 追加式存储不可篡改 (M3)."""
import datetime as dt
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.logging import get_logger

logger = get_logger(__name__)


class AuditLog(Base):
    """审计日志: 谁 / 何时 / 做了什么 / 目标是什么."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), default="default", index=True)  # M7 多租户
    actor: Mapped[str] = mapped_column(String(128), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    target_type: Mapped[str] = mapped_column(String(32), default="")
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())


async def record_audit(
    actor: str,
    action: str,
    target_type: str = "",
    target_id: Any = None,
    detail: dict | None = None,
    tenant: str = "default",
) -> None:
    """记录审计日志: 独立会话写入, 与业务事务解耦, 失败不影响主流程."""
    try:
        from app.core.database import SessionLocal

        async with SessionLocal() as session:
            session.add(
                AuditLog(
                    tenant_id=tenant,
                    actor=actor,
                    action=action,
                    target_type=target_type,
                    target_id=str(target_id) if target_id is not None else None,
                    detail=detail,
                )
            )
            await session.commit()
    except Exception:
        await session.rollback()
        logger.exception("审计日志写入失败: %s/%s", actor, action)


async def list_audit_logs(
    session: AsyncSession,
    limit: int = 200,
    action: str | None = None,
    actor: str | None = None,
    tenant: str = "default",
) -> list[AuditLog]:
    stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if actor:
        stmt = stmt.where(AuditLog.actor == actor)
    result = await session.execute(stmt)
    return list(result.scalars().all())
