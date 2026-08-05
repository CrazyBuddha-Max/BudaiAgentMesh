"""效果反馈层: 任务反馈 (点赞/点踩/评分/评论) 与统计 (M3)."""
import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.exceptions import BizError, NotFoundError
from app.core.logging import get_logger

logger = get_logger(__name__)


class TaskFeedback(Base):
    """反馈与任务/Trace 绑定, 可回溯到具体执行."""

    __tablename__ = "task_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("agent_tasks.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[int] = mapped_column(Integer, index=True)
    rating: Mapped[int] = mapped_column(Integer, default=3)  # 1-5
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())


async def submit_feedback(
    session: AsyncSession,
    task_id: int,
    rating: int,
    comment: str | None,
    actor: str,
) -> TaskFeedback:
    from app.agents.models import AgentTask

    if not 1 <= rating <= 5:
        raise BizError("评分需在 1-5 之间")
    task = await session.get(AgentTask, task_id)
    if task is None:
        raise NotFoundError(f"任务不存在: {task_id}")
    fb = TaskFeedback(
        task_id=task_id,
        agent_id=task.agent_id,
        rating=rating,
        comment=comment,
        created_by=actor,
    )
    session.add(fb)
    await session.commit()
    await session.refresh(fb)
    return fb


async def feedback_stats(session: AsyncSession) -> dict:
    total = await session.scalar(select(func.count(TaskFeedback.id))) or 0
    avg = await session.scalar(select(func.avg(TaskFeedback.rating))) or 0.0
    by_rating = {}
    rows = await session.execute(
        select(TaskFeedback.rating, func.count(TaskFeedback.id)).group_by(TaskFeedback.rating)
    )
    for rating, count in rows:
        by_rating[str(rating)] = count
    return {
        "total": total,
        "avg_rating": round(float(avg), 2),
        "by_rating": by_rating,
    }
