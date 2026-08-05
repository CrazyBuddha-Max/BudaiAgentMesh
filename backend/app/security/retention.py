"""数据生命周期治理 (M5): 保留期策略与状态评估.

规则: 数据源设置 retention_days, 自最近采集时间起算;
到期标记 expired (数据应归档/销毁), 临期 7 天内标记 expiring.
"""
import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.access.models import DataSource

LIFECYCLE_LABELS = {
    "no-policy": "无策略",
    "active": "活跃",
    "expiring": "临期",
    "expired": "已过期",
}


def lifecycle_status(source: DataSource, now: dt.datetime | None = None) -> str:
    """评估数据源生命周期状态."""
    if not source.retention_days or source.retention_days <= 0:
        return "no-policy"
    base = source.last_ingested_at or source.created_at
    if base is None:
        return "no-policy"
    now = now or dt.datetime.now(dt.UTC)
    if base.tzinfo is None:
        base = base.replace(tzinfo=dt.UTC)
    expires = base + dt.timedelta(days=source.retention_days)
    if now >= expires:
        return "expired"
    if (expires - now).days < 7:
        return "expiring"
    return "active"


async def list_lifecycle(session: AsyncSession) -> list[dict]:
    """导出全部数据源的生命周期视图."""
    result = await session.execute(select(DataSource).order_by(DataSource.created_at.desc()))
    sources = list(result.scalars().all())
    items = []
    for src in sources:
        status = lifecycle_status(src)
        base = src.last_ingested_at or src.created_at
        expires = None
        if src.retention_days and base:
            expires = base + dt.timedelta(days=src.retention_days)
        items.append(
            {
                "source_id": src.id,
                "source_name": src.name,
                "source_type": src.source_type,
                "retention_days": src.retention_days,
                "status": status,
                "status_label": LIFECYCLE_LABELS.get(status, status),
                "last_ingested_at": src.last_ingested_at.isoformat() if src.last_ingested_at else None,
                "expires_at": expires.isoformat() if expires else None,
            }
        )
    return items


async def summary(session: AsyncSession) -> dict:
    """生命周期统计: 各状态数量."""
    items = await list_lifecycle(session)
    counts: dict[str, int] = {}
    for item in items:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return {"total": len(items), "by_status": counts}
