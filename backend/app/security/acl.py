"""细粒度列级权限 (M5): 按角色禁止访问指定列.

默认全开放, 通过 deny 规则收敛: (角色, 表, 列) -> 禁止.
作用域: 数据采样 / 指标维度下钻 (与动态脱敏叠加使用).
"""
import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Integer, String, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.exceptions import BizError, NotFoundError


class ColumnPolicy(Base):
    """列权限规则: 角色在指定表上禁止访问的列."""

    __tablename__ = "column_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role: Mapped[str] = mapped_column(String(32), index=True)  # viewer/analyst/admin
    table_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_tables.id", ondelete="CASCADE"), nullable=True)
    column_name: Mapped[str] = mapped_column(String(255))  # 支持 * 表示整表禁止
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())


async def create_policy(
    session: AsyncSession,
    role: str,
    column_name: str,
    table_id: int | None = None,
    actor: str = "system",
) -> ColumnPolicy:
    if role not in ("viewer", "analyst", "admin"):
        raise BizError(f"未知角色: {role}")
    if table_id is not None:
        from app.access.catalog import get_table

        table = await get_table(session, table_id)
        if column_name != "*" and column_name not in {c.column_name for c in table.columns}:
            raise BizError(f"列 {column_name!r} 不在表 {table.table_name} 中")
    policy = ColumnPolicy(role=role, table_id=table_id, column_name=column_name, created_by=actor)
    session.add(policy)
    await session.commit()
    await session.refresh(policy)
    return policy


async def delete_policy(session: AsyncSession, policy_id: int) -> None:
    policy = await session.get(ColumnPolicy, policy_id)
    if policy is None:
        raise NotFoundError(f"列权限规则不存在: {policy_id}")
    await session.delete(policy)
    await session.commit()


async def list_policies(session: AsyncSession, role: str | None = None) -> list[ColumnPolicy]:
    stmt = select(ColumnPolicy).order_by(ColumnPolicy.created_at.desc())
    if role:
        stmt = stmt.where(ColumnPolicy.role == role)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def denied_columns(session: AsyncSession, role: str, table_id: int) -> set[str]:
    """返回角色在指定表上被禁止的列集合 (含 * 通配)."""
    stmt = select(ColumnPolicy).where(ColumnPolicy.role == role).where(
        (ColumnPolicy.table_id == table_id) | (ColumnPolicy.table_id.is_(None))
    )
    result = await session.execute(stmt)
    return {p.column_name for p in result.scalars().all()}


def apply_column_acl(rows: list[dict], denied: set[str]) -> list[dict]:
    """从结果行中剔除被禁止的列."""
    if not denied:
        return rows
    if "*" in denied:
        return []
    masked: list[dict] = []
    for row in rows:
        masked.append({k: v for k, v in row.items() if k not in denied})
    return masked
