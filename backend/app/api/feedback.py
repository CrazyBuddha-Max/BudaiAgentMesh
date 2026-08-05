"""效果反馈 API: 任务反馈 + 统计."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.feedback.feedback import feedback_stats, submit_feedback
from app.security.auth import AnalystDep, CurrentUserDep

router = APIRouter()

SessionDep = Depends(get_session)


class FeedbackCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = None


class FeedbackOut(BaseModel):
    id: int
    task_id: int
    agent_id: int
    rating: int
    comment: str | None = None
    created_by: str | None = None
    created_at: object = None


@router.post("/tasks/{task_id}/feedback", response_model=FeedbackOut, status_code=201)
async def submit_task_feedback(
    task_id: int,
    payload: FeedbackCreate,
    user: AnalystDep,
    session: AsyncSession = SessionDep,
):
    """提交任务反馈 (1-5 星 + 评论), 绑定任务/Trace 可回溯 (M3)."""
    fb = await submit_feedback(session, task_id, payload.rating, payload.comment, user.username)
    return FeedbackOut(
        id=fb.id,
        task_id=fb.task_id,
        agent_id=fb.agent_id,
        rating=fb.rating,
        comment=fb.comment,
        created_by=fb.created_by,
        created_at=fb.created_at.isoformat(),
    )


@router.get("/stats")
async def stats(user: CurrentUserDep, session: AsyncSession = SessionDep) -> dict:
    """反馈统计: 总量 / 平均分 / 评分分布 (驱动迭代闭环)."""
    return await feedback_stats(session)


@router.get("/metrics")
async def metrics(user: CurrentUserDep) -> dict:
    """运行指标快照 (近 5 分钟请求量/时延/错误率)."""
    from app.feedback.metrics import snapshot

    return snapshot()
