"""数据血缘: 源表 -> 指标 -> 任务 -> 结果 全链路可追溯 (M3)."""
import datetime as dt
from typing import Any

from sqlalchemy import DateTime, Integer, String, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.logging import get_logger

logger = get_logger(__name__)


class LineageEdge(Base):
    """血缘边: from (数据提供方) -> to (数据消费方)."""

    __tablename__ = "lineage_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_type: Mapped[str] = mapped_column(String(32), index=True)  # table/metric/doc/source
    from_id: Mapped[str] = mapped_column(String(64))
    to_type: Mapped[str] = mapped_column(String(32), index=True)  # metric/task/query
    to_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64), default="derives")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())


async def record_lineage(
    from_type: str,
    from_id: Any,
    to_type: str,
    to_id: Any,
    action: str = "consumed_by",
) -> None:
    """记录血缘边: 独立会话写入, 与业务事务解耦, 失败不影响主流程."""
    try:
        from app.core.database import SessionLocal

        async with SessionLocal() as session:
            session.add(
                LineageEdge(
                    from_type=from_type,
                    from_id=str(from_id),
                    to_type=to_type,
                    to_id=str(to_id),
                    action=action,
                )
            )
            await session.commit()
    except Exception:
        logger.exception("血缘记录失败: %s:%s -> %s:%s", from_type, from_id, to_type, to_id)


async def build_lineage_graph(session: AsyncSession, limit: int = 500) -> dict:
    """导出图结构: {nodes: [{id, type, label}], edges: [{from, to, action}]}."""
    result = await session.execute(select(LineageEdge).order_by(LineageEdge.created_at.desc()).limit(limit))
    edges = list(result.scalars().all())

    nodes: dict[str, dict] = {}
    for edge in edges:
        for node_type, node_id, node_kind in (
            (edge.from_type, edge.from_id, "source"),
            (edge.to_type, edge.to_id, "consumer"),
        ):
            key = f"{node_type}:{node_id}"
            if key not in nodes:
                nodes[key] = {"id": key, "type": node_type, "kind": node_kind, "label": node_id}

    return {
        "nodes": list(nodes.values()),
        "edges": [
            {"from": f"{e.from_type}:{e.from_id}", "to": f"{e.to_type}:{e.to_id}", "action": e.action}
            for e in edges
        ],
    }
