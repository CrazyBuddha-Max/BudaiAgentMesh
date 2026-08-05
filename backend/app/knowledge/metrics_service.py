"""指标语义层服务: 定义管理 + 查询执行 (口径即契约).

查询链路: 指标定义 -> 绑定表 -> 连接器 query_aggregate -> 结果.
所有度量表达式经 expr.py 白名单校验, 杜绝注入.
"""
import datetime as dt
import time

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.access.catalog import get_source, get_table, source_params
from app.access.connectors import registry
from app.access.connectors.expr import (
    ExprError,
    validate_expr_columns,
)
from app.access.models import CatalogTable, DataSource
from app.core.exceptions import BizError, NotFoundError
from app.knowledge.metrics_models import AGGREGATIONS, MetricDefinition
from app.knowledge.metrics_schemas import (
    MetricOut,
    MetricQueryRequest,
    MetricQueryResult,
    SourceBrief,
    TableBrief,
)


async def list_metrics(
    session: AsyncSession, keyword: str | None = None, status: str | None = None, limit: int = 200
) -> list[MetricDefinition]:
    stmt = select(MetricDefinition).order_by(MetricDefinition.created_at.desc()).limit(limit)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                MetricDefinition.name.ilike(like),
                MetricDefinition.display_name.ilike(like),
                MetricDefinition.description.ilike(like),
            )
        )
    if status:
        stmt = stmt.where(MetricDefinition.status == status)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_metric(session: AsyncSession, metric_id: int) -> MetricDefinition:
    metric = await session.get(MetricDefinition, metric_id)
    if metric is None:
        raise NotFoundError(f"指标不存在: {metric_id}")
    return metric


async def create_metric(session: AsyncSession, payload) -> MetricDefinition:
    table = await get_table(session, payload.table_id)
    column_names = {c.column_name for c in table.columns}

    # 表达式白名单校验: 引用的列必须已注册
    try:
        validate_expr_columns(payload.measure, column_names)
    except ExprError as exc:
        raise BizError(str(exc)) from exc
    if payload.aggregation not in AGGREGATIONS:
        raise BizError(f"不支持的聚合方式: {payload.aggregation}, 可选 {AGGREGATIONS}")
    for dim in payload.dimensions:
        if dim not in column_names:
            raise BizError(f"维度列未注册: {dim}")

    metric = MetricDefinition(
        name=payload.name,
        display_name=payload.display_name,
        description=payload.description,
        table_id=payload.table_id,
        measure=payload.measure,
        aggregation=payload.aggregation,
        dimensions=payload.dimensions,
        default_filters=[f.model_dump() for f in payload.default_filters] if payload.default_filters else None,
        unit=payload.unit,
        owner=payload.owner,
        status="active",
    )
    session.add(metric)
    try:
        await session.commit()
    except Exception as exc:
        await session.rollback()
        raise BizError(f"指标创建失败 (名称可能重复): {exc}") from exc
    await session.refresh(metric)
    return metric


async def delete_metric(session: AsyncSession, metric_id: int) -> None:
    metric = await get_metric(session, metric_id)
    await session.delete(metric)
    await session.commit()


async def to_out(session: AsyncSession, metric: MetricDefinition) -> MetricOut:
    """组装输出: 附加绑定表与数据源信息."""
    table = await session.get(CatalogTable, metric.table_id)
    source: DataSource | None = None
    table_brief: TableBrief | None = None
    if table is not None:
        source = await session.get(DataSource, table.source_id)
        table_brief = TableBrief(
            id=table.id,
            schema_name=table.schema_name,
            table_name=table.table_name,
            row_count=table.row_count,
            quality_score=table.quality_score,
        )
    return MetricOut(
        id=metric.id,
        name=metric.name,
        display_name=metric.display_name,
        description=metric.description,
        table_id=metric.table_id,
        measure=metric.measure,
        expression=metric.measure,
        aggregation=metric.aggregation,
        dimensions=metric.dimensions,
        default_filters=metric.default_filters,
        unit=metric.unit,
        owner=metric.owner,
        status=metric.status,
        created_at=metric.created_at,
        updated_at=metric.updated_at,
        table=table_brief,
        source=SourceBrief(id=source.id, name=source.name, source_type=source.source_type) if source else None,
    )


async def query_metric(
    session: AsyncSession,
    metric_id: int,
    request: MetricQueryRequest,
    actor: str | None = None,
    role: str | None = None,
) -> MetricQueryResult:
    from app.security.audit import record_audit
    from app.security.lineage import record_lineage
    from app.security.masking import apply_masking, detect_sensitive_columns

    metric = await get_metric(session, metric_id)
    table = await get_table(session, metric.table_id)
    source = await get_source(session, table.source_id)

    # 维度校验: 仅允许该指标声明的维度 (防止越权下钻)
    for dim in request.group_by:
        if dim not in metric.dimensions:
            raise BizError(f"维度 {dim!r} 不在指标允许范围内: {metric.dimensions}")

    filters = [f.model_dump() for f in request.filters] if request.filters else None

    connector = registry.build(source.source_type, source_params(source))
    started = time.monotonic()
    try:
        rows = await connector.query_aggregate(
            table=table.table_name,
            aggregation=metric.aggregation,
            measure=metric.measure,
            group_by=request.group_by or None,
            filters=filters,
            limit=request.limit,
        )
    finally:
        await connector.close()
    duration_ms = int((time.monotonic() - started) * 1000)

    # 维度值脱敏 (如按 customer_name 下钻时, viewer/analyst 看到掩码)
    if request.group_by:
        sensitive = detect_sensitive_columns(request.group_by)
        rows = apply_masking(rows, sensitive, role or "viewer")

    await record_audit(
        actor or "system", "metric.query", "metric", metric.id,
        {"metric": metric.name, "table": f"{table.schema_name}.{table.table_name}", "group_by": request.group_by},
    )
    await record_lineage("table", table.id, "metric", metric.id, action="aggregated_by")

    metric_out = await to_out(session, metric)
    return MetricQueryResult(
        metric=metric_out,
        source={
            "id": source.id,
            "name": source.name,
            "source_type": source.source_type,
            "schema": table.schema_name,
            "table": table.table_name,
        },
        expression=metric.measure,
        group_by=request.group_by,
        rows=rows,
        duration_ms=duration_ms,
        executed_at=dt.datetime.now(dt.UTC),
    )
