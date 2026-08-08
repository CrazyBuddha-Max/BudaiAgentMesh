"""采集引擎: 连接数据源 -> 发现 Schema -> 质量初检 -> 写入元数据目录."""
import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession

from app.access import models
from app.access.catalog import get_source, source_params
from app.access.connectors import TableProfile, registry
from app.core.logging import get_logger

logger = get_logger(__name__)


async def test_source(session: AsyncSession, source_id: int, tenant: str = "default") -> str:
    """连接校验: 通过则置为 active, 失败置为 error 并抛出异常."""
    source = await get_source(session, source_id, tenant=tenant)
    try:
        connector = registry.build(source.source_type, source_params(source))
        await connector.test_connection()
        await connector.close()
        source.status = "active"
        await session.commit()
        return "连接成功"
    except Exception:
        source.status = "error"
        await session.commit()
        raise


async def ingest_source(
    session: AsyncSession, source_id: int, tenant: str = "default"
) -> models.IngestionRun:
    """执行一次采集: 增量检测 -> Schema 注册 + 质量初检 + 目录落库."""
    source = await get_source(session, source_id, tenant=tenant)
    run = models.IngestionRun(source_id=source_id, status="running")
    session.add(run)
    await session.commit()
    await session.refresh(run)

    from app.core.telemetry import span

    async with span("ingest.source", source_id=source_id, source_type=source.source_type):
        try:
            connector = registry.build(source.source_type, source_params(source))
            await connector.test_connection()

            # 增量检测 (M6): 无变化则跳过重采, 保留目录现状
            change = await connector.detect_changes(source.watermark)
            if not change["changed"]:
                await connector.close()
                source.status = "active"
                source.last_ingested_at = dt.datetime.now(dt.UTC)
                run.status = "success"
                run.tables_found = 0
                run.message = change.get("detail", "无变化, 增量跳过")
                run.finished_at = dt.datetime.now(dt.UTC)
                await session.commit()
                return run

            profiles: list[TableProfile] = await connector.discover_schema()
            await connector.close()

            await _sync_catalog(session, source, profiles)
            table_count = len(profiles)
            source.status = "active"
            source.last_ingested_at = dt.datetime.now(dt.UTC)
            source.quality_score = _overall_quality(profiles)
            source.watermark = change.get("watermark")
            run.status = "success"
            run.tables_found = table_count
            run.message = f"发现 {table_count} 张表 ({change.get('detail', '全量')})"
            run.finished_at = dt.datetime.now(dt.UTC)
            await session.commit()
        except Exception as exc:
            logger.exception("采集失败 source_id=%s", source_id)
            source.status = "error"
            run.status = "failed"
            run.message = str(exc)
            run.finished_at = dt.datetime.now(dt.UTC)
            await session.commit()
            raise
    return run


async def _sync_catalog(
    session: AsyncSession, source: models.DataSource, profiles: list[TableProfile]
) -> None:
    """以画像结果为准做增量同步: 表存在则更新, 不存在则创建."""
    from sqlalchemy import select

    for profile in profiles:
        stmt = select(models.CatalogTable).where(
            models.CatalogTable.source_id == source.id,
            models.CatalogTable.table_name == profile.table_name,
        )
        table = (await session.execute(stmt)).scalar_one_or_none()
        if table is None:
            table = models.CatalogTable(
                source_id=source.id,
                schema_name=profile.schema_name,
                table_name=profile.table_name,
                row_count=profile.row_count,
                quality_score=_table_quality(profile),
            )
            session.add(table)
            await session.flush()
        else:
            table.row_count = profile.row_count
            table.quality_score = _table_quality(profile)
            table.schema_name = profile.schema_name
            await session.flush()

        # 列级全量重建 (简单可靠; 增量需引入变更检测, 留待 M5)
        await session.execute(
            models.CatalogColumn.__table__.delete().where(models.CatalogColumn.table_id == table.id)
        )
        for col in profile.columns:
            session.add(
                models.CatalogColumn(
                    table_id=table.id,
                    column_name=col.name,
                    data_type=col.data_type,
                    is_nullable=col.is_nullable,
                    is_primary_key=col.is_primary_key,
                    null_rate=col.null_rate,
                    distinct_ratio=col.distinct_ratio,
                    sample_values=col.sample_values,
                )
            )


def _table_quality(profile: TableProfile) -> float:
    """表级质量分: 由各列空值率/区分度综合, 0~100."""
    if not profile.columns:
        return 0.0
    scores = []
    for col in profile.columns:
        completeness = 1.0 - col.null_rate
        if col.distinct_ratio <= 0:
            info = 0.0
        elif col.distinct_ratio >= 1.0:
            info = 1.0
        else:
            info = min(col.distinct_ratio * 4, 1.0)  # 区分度过低视为弱信息列
        scores.append(0.7 * completeness + 0.3 * info)
    return round(sum(scores) / len(scores) * 100, 1)


def _overall_quality(profiles: list[TableProfile]) -> float:
    if not profiles:
        return 0.0
    return round(sum(_table_quality(p) for p in profiles) / len(profiles), 1)
