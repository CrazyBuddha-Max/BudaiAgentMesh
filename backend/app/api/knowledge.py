"""知识沉淀层 API: 指标语义层 (指标 CRUD + 可执行查询)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.knowledge.schemas import (
    MetricCreate,
    MetricOut,
    MetricQueryRequest,
    MetricQueryResult,
    MetricUpdate,
)
from app.knowledge.service import (
    _to_metric_out,
    create_metric,
    delete_metric,
    get_metric,
    list_metrics,
    query_metric,
    update_metric,
)
from app.security.auth import AdminDep, AnalystDep, CurrentUserDep

router = APIRouter()

SessionDep = Depends(get_session)


@router.get("/metrics", response_model=list[MetricOut])
async def metrics(
    keyword: str | None = Query(default=None, description="按指标名 / 口径检索"),
    source_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    user: CurrentUserDep = None,
    session: AsyncSession = SessionDep,
) -> list[dict]:
    return await list_metrics(session, keyword=keyword, source_id=source_id, status=status)


@router.post("/metrics", response_model=MetricOut, status_code=201)
async def create(
    payload: MetricCreate,
    user: AnalystDep,
    session: AsyncSession = SessionDep,
) -> dict:
    return await create_metric(session, payload)


@router.get("/metrics/{metric_id}", response_model=MetricOut)
async def detail(
    metric_id: int,
    user: CurrentUserDep,
    session: AsyncSession = SessionDep,
) -> dict:
    metric = await get_metric(session, metric_id)
    return await _to_metric_out(session, metric)


@router.patch("/metrics/{metric_id}", response_model=MetricOut)
async def update(
    metric_id: int,
    payload: MetricUpdate,
    user: AnalystDep,
    session: AsyncSession = SessionDep,
) -> dict:
    return await update_metric(session, metric_id, payload)


@router.delete("/metrics/{metric_id}", status_code=204)
async def remove(
    metric_id: int,
    user: AdminDep,
    session: AsyncSession = SessionDep,
) -> None:
    await delete_metric(session, metric_id)


@router.post("/metrics/{metric_id}/query", response_model=MetricQueryResult)
async def run_query(
    metric_id: int,
    payload: MetricQueryRequest,
    user: AnalystDep,
    session: AsyncSession = SessionDep,
) -> dict:
    metric = await get_metric(session, metric_id)
    return await query_metric(session, metric, payload)
