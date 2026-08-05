"""知识沉淀层服务 (指标语义层): 指标 CRUD + 可执行查询.

口径原则 (架构文档 3.2): Agent 调用指标时拿到的是
"口径正确的数字 + 可追溯的定义", 因此每次查询结果都携带
指标定义、来源表、来源数据源与生成的表达式。
"""
import datetime as dt
import time

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import models as access_models
from app.access.catalog import source_params
from app.access.connectors import registry
from app.access.connectors.expr import ExprError, validate_expr_columns
from app.core.exceptions import BizError, NotFoundError
from app.knowledge import models as knowledge_models
from app.knowledge.schemas import MetricCreate, MetricQueryRequest, MetricUpdate

_METRIC_STATUSES = ("active", "archived")


# ---------- 指标 CRUD ----------

async def list_metrics(
    session: AsyncSession,
    keyword: str | None = None,
    source_id: int | None = None,
    status: str | None = None,
) -> list[dict]:
    stmt = select(knowledge_models.MetricDefinition).order_by(
        knowledge_models.MetricDefinition.updated_at.desc()
    )
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                knowledge_models.MetricDefinition.name.ilike(like),
                knowledge_models.MetricDefinition.display_name.ilike(like),
                knowledge_models.MetricDefinition.description.ilike(like),
            )
        )
    if source_id:
        stmt = stmt.join(access_models.CatalogTable).where(
            access_models.CatalogTable.source_id == source_id
        )
    if status:
        stmt = stmt.where(knowledge_models.MetricDefinition.status == status)
    result = await session.execute(stmt)
    metrics = list(result.scalars().all())
    return [await _to_metric_out(session, m) for m in metrics]


async def get_metric(
    session: AsyncSession, metric_id: int
) -> knowledge_models.MetricDefinition:
    metric = await session.get(knowledge_models.MetricDefinition, metric_id)
    if metric is None:
        raise NotFoundError(f"指标不存在: {metric_id}")
    return metric


async def _to_metric_out(
    session: AsyncSession, metric: knowledge_models.MetricDefinition
) -> dict:
    """组装指标输出: 附上来源表 / 来源数据源 (在异步会话内完成加载)."""
    table = await session.get(access_models.CatalogTable, metric.table_id)
    source = await session.get(access_models.DataSource, table.source_id) if table else None
    return {
        "id": metric.id,
        "name": metric.name,
        "display_name": metric.display_name,
        "description": metric.description,
        "table_id": metric.table_id,
        "measure": metric.measure,
        "aggregation": metric.aggregation,
        "dimensions": metric.dimensions or [],
        "default_filters": metric.default_filters or [],
        "unit": metric.unit,
        "owner": metric.owner,
        "status": metric.status,
        "created_at": metric.created_at,
        "updated_at": metric.updated_at,
        "expression": metric.expression,
        "table": {
            "id": table.id,
            "schema_name": table.schema_name,
            "table_name": table.table_name,
            "row_count": table.row_count,
            "quality_score": table.quality_score,
        }
        if table
        else None,
        "source": {"id": source.id, "name": source.name, "source_type": source.source_type}
        if source
        else None,
    }


def _column_names(table: access_models.CatalogTable) -> set[str]:
    return {c.column_name for c in table.columns}


def _validate_metric(
    table: access_models.CatalogTable, payload: MetricCreate | MetricUpdate
) -> None:
    """校验度量表达式 / 维度 / 口径条件均绑定到已注册的列."""
    columns = _column_names(table)
    measure = payload.measure if payload.measure is not None else None
    if measure is not None:
        try:
            validate_expr_columns(measure, columns)
        except ExprError as exc:
            raise BizError(str(exc)) from exc
    for dimension in payload.dimensions or []:
        if dimension not in columns:
            raise BizError(f"维度列未在目录中注册: {dimension!r}")
    for rule in payload.default_filters or []:
        if rule.column not in columns:
            raise BizError(f"口径条件引用了未注册的列: {rule.column!r}")


async def create_metric(
    session: AsyncSession, payload: MetricCreate
) -> knowledge_models.MetricDefinition:
    table = await session.get(access_models.CatalogTable, payload.table_id)
    if table is None:
        raise NotFoundError(f"目录表不存在: {payload.table_id}")
    existing = await session.scalar(
        select(knowledge_models.MetricDefinition).where(
            knowledge_models.MetricDefinition.name == payload.name
        )
    )
    if existing is not None:
        raise BizError(f"指标名称已存在: {payload.name}", code="DUPLICATE_METRIC")
    _validate_metric(table, payload)
    metric = knowledge_models.MetricDefinition(**payload.model_dump())
    session.add(metric)
    await session.commit()
    await session.refresh(metric)
    return await _to_metric_out(session, metric)


async def update_metric(
    session: AsyncSession, metric_id: int, payload: MetricUpdate
) -> knowledge_models.MetricDefinition:
    metric = await get_metric(session, metric_id)
    data = payload.model_dump(exclude_unset=True)
    if data:
        table = await session.get(access_models.CatalogTable, metric.table_id)
        if table is not None:
            _validate_metric(table, payload)
        for key, value in data.items():
            setattr(metric, key, value)
        await session.commit()
        await session.refresh(metric)
    return await _to_metric_out(session, metric)


async def delete_metric(session: AsyncSession, metric_id: int) -> None:
    metric = await get_metric(session, metric_id)
    await session.delete(metric)
    await session.commit()


# ---------- 指标查询 ----------

async def query_metric(
    session: AsyncSession,
    metric: knowledge_models.MetricDefinition,
    request: MetricQueryRequest,
) -> dict:
    """执行指标查询: 解析来源 -> 校验维度/过滤 -> 连接器聚合 -> 返回可追溯结果."""
    table = await session.get(access_models.CatalogTable, metric.table_id)
    if table is None:
        raise NotFoundError(f"指标绑定的目录表不存在: {metric.table_id}")
    source = await session.get(access_models.DataSource, table.source_id)
    if source is None:
        raise NotFoundError(f"指标绑定的数据源不存在: {table.source_id}")

    columns = _column_names(table)
    metric_dims = set(metric.dimensions or [])
    group_by = request.group_by or []
    for dim in group_by:
        if dim not in metric_dims:
            raise BizError(f"维度 {dim!r} 不在指标允许的维度范围内: {sorted(metric_dims)}")
        if dim not in columns:
            raise BizError(f"维度列未在目录中注册: {dim!r}")
    for rule in request.filters:
        if rule.column not in columns:
            raise BizError(f"过滤条件引用了未注册的列: {rule.column!r}")
    if metric.measure.strip() != "*":
        try:
            validate_expr_columns(metric.measure, columns)
        except ExprError as exc:
            raise BizError(str(exc)) from exc

    connector = registry.build(source.source_type, source_params(source))
    started = time.perf_counter()
    try:
        rows = await connector.query_aggregate(
            table=table.table_name,
            aggregation=metric.aggregation,
            measure=metric.measure,
            group_by=group_by or None,
            filters=[r.model_dump() for r in request.filters],
            limit=request.limit,
        )
    finally:
        await connector.close()
    duration_ms = round((time.perf_counter() - started) * 1000, 2)

    metric_out = await _to_metric_out(session, metric)
    return {
        "metric": metric_out,
        "source": {
            "id": source.id,
            "name": source.name,
            "source_type": source.source_type,
            "schema": table.schema_name,
            "table": table.table_name,
        },
        "expression": metric.expression,
        "group_by": group_by,
        "rows": rows,
        "duration_ms": duration_ms,
        "executed_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
    }

