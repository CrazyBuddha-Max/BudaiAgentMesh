"""元数据目录服务: 数据源 CRUD / 目录浏览 / 字段搜索."""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import models
from app.access.connectors import registry
from app.access.crypto import decrypt_secret, encrypt_secret
from app.access.schemas import SourceCreate, SourceUpdate
from app.core.exceptions import NotFoundError


async def list_sources(session: AsyncSession) -> list[models.DataSource]:
    result = await session.execute(select(models.DataSource).order_by(models.DataSource.created_at.desc()))
    return list(result.scalars().all())


async def get_source(session: AsyncSession, source_id: int) -> models.DataSource:
    source = await session.get(models.DataSource, source_id)
    if source is None:
        raise NotFoundError(f"数据源不存在: {source_id}")
    return source


async def create_source(session: AsyncSession, payload: SourceCreate) -> models.DataSource:
    source = models.DataSource(
        name=payload.name,
        source_type=payload.source_type,
        description=payload.description,
        host=payload.host,
        port=payload.port,
        database=payload.database,
        schema_name=payload.schema_name,
        username=payload.username,
        password_enc=encrypt_secret(payload.password),
        file_path=payload.file_path,
        status="pending",
    )
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return source


async def update_source(
    session: AsyncSession, source_id: int, payload: SourceUpdate
) -> models.DataSource:
    source = await get_source(session, source_id)
    data = payload.model_dump(exclude_unset=True)
    if "password" in data:
        source.password_enc = encrypt_secret(data.pop("password"))
    for key, value in data.items():
        if value is not None:
            setattr(source, key, value)
    source.status = "pending"  # 连接参数变更后需重新校验
    await session.commit()
    await session.refresh(source)
    return source


async def delete_source(session: AsyncSession, source_id: int) -> None:
    source = await get_source(session, source_id)
    await session.delete(source)
    await session.commit()


def source_params(source: models.DataSource) -> dict:
    """组装连接器参数 (密文口令仅在内存中解密)."""
    return {
        "host": source.host,
        "port": source.port,
        "database": source.database,
        "schema_name": source.schema_name,
        "username": source.username,
        "password": decrypt_secret(source.password_enc),
        "file_path": source.file_path,
    }


async def list_tables(
    session: AsyncSession,
    source_id: int | None = None,
    keyword: str | None = None,
    limit: int = 100,
) -> list[models.CatalogTable]:
    stmt = select(models.CatalogTable).order_by(models.CatalogTable.table_name).limit(limit)
    if source_id is not None:
        stmt = stmt.where(models.CatalogTable.source_id == source_id)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            or_(models.CatalogTable.table_name.ilike(like), models.CatalogTable.description.ilike(like))
        )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_table(session: AsyncSession, table_id: int) -> models.CatalogTable:
    table = await session.get(models.CatalogTable, table_id)
    if table is None:
        raise NotFoundError(f"目录表不存在: {table_id}")
    return table


async def search_columns(
    session: AsyncSession, keyword: str, limit: int = 50
) -> list[models.CatalogColumn]:
    like = f"%{keyword}%"
    stmt = (
        select(models.CatalogColumn)
        .where(models.CatalogColumn.column_name.ilike(like))
        .order_by(models.CatalogColumn.column_name)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def catalog_stats(session: AsyncSession) -> dict:
    """目录总览统计, 供数据资产门户首页展示."""
    sources = await session.scalar(select(func.count(models.DataSource.id))) or 0
    tables = await session.scalar(select(func.count(models.CatalogTable.id))) or 0
    columns = await session.scalar(select(func.count(models.CatalogColumn.id))) or 0
    runs = await session.scalar(select(func.count(models.IngestionRun.id))) or 0
    return {
        "sources": sources,
        "tables": tables,
        "columns": columns,
        "ingestion_runs": runs,
    }


async def query_table_rows(
    session: AsyncSession,
    table_id: int,
    limit: int = 10,
    actor: str | None = None,
    role: str | None = None,
) -> dict:
    """读取表数据样例 (Agent 数据工具): 经连接器契约执行, 全程受控.

    安全三件套 (M3): 动态脱敏 (按角色) + 审计留痕 + 血缘记录.
    """
    from app.security.audit import record_audit
    from app.security.lineage import record_lineage
    from app.security.masking import apply_masking, detect_sensitive_columns

    table = await get_table(session, table_id)
    source = await get_source(session, table.source_id)
    connector = registry.build(source.source_type, source_params(source))
    try:
        rows = await connector.sample_rows(table.table_name, limit=limit)
    finally:
        await connector.close()

    # 敏感列识别 + 动态脱敏
    sensitive = detect_sensitive_columns([c.column_name for c in table.columns])
    masked_rows = apply_masking(rows, sensitive, role or "viewer")
    masked_count = sum(1 for c in sensitive if any(c in r for r in rows))

    # 审计 + 血缘
    await record_audit(
        actor or "system", "data.sample", "table", table.id,
        {"table": f"{table.schema_name}.{table.table_name}", "rows": len(rows), "masked": bool(sensitive)},
    )
    await record_lineage("table", table.id, "query", f"sample-{table.id}", action="sampled_by")

    return {
        "table_id": table.id,
        "table_name": f"{table.schema_name}.{table.table_name}",
        "source": source.name,
        "row_count": table.row_count,
        "rows": masked_rows,
        "masking": {"enabled": bool(sensitive), "masked_columns": masked_count},
    }
