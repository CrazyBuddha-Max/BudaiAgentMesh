"""元数据目录服务: 数据源 CRUD / 目录浏览 / 字段搜索."""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import models
from app.access.connectors import registry
from app.access.crypto import decrypt_secret, encrypt_secret
from app.access.schemas import SourceCreate, SourceUpdate
from app.core.exceptions import NotFoundError


async def list_sources(session: AsyncSession, tenant: str = "default") -> list[models.DataSource]:
    stmt = (
        select(models.DataSource)
        .where(models.DataSource.tenant_id == tenant)
        .order_by(models.DataSource.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_source(session: AsyncSession, source_id: int, tenant: str = "default") -> models.DataSource:
    source = await session.get(models.DataSource, source_id)
    if source is None:
        raise NotFoundError(f"数据源不存在: {source_id}")
    if source.tenant_id != tenant:  # M6 多租户: 越权访问视为不存在
        raise NotFoundError(f"数据源不存在: {source_id}")
    return source


async def create_source(
    session: AsyncSession, payload: SourceCreate, tenant: str = "default"
) -> models.DataSource:
    source = models.DataSource(
        name=payload.name,
        tenant_id=tenant,
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
    session: AsyncSession, source_id: int, payload: SourceUpdate, tenant: str = "default"
) -> models.DataSource:
    source = await get_source(session, source_id, tenant=tenant)
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


async def delete_source(session: AsyncSession, source_id: int, tenant: str = "default") -> None:
    source = await get_source(session, source_id, tenant=tenant)
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
    tenant: str = "default",
) -> list[models.CatalogTable]:
    stmt = select(models.CatalogTable).order_by(models.CatalogTable.table_name).limit(limit)
    if source_id is not None:
        stmt = stmt.where(models.CatalogTable.source_id == source_id)
    else:
        # M6 多租户: 未指定数据源时仅返回本租户目录 (通过数据源归属过滤)
        tenant_sources = select(models.DataSource.id).where(models.DataSource.tenant_id == tenant)
        stmt = stmt.where(models.CatalogTable.source_id.in_(tenant_sources))
    if keyword:
        # M7: 中英同义词映射 + 关键词拆分, 让中文检索能命中英文表名 (订单 -> orders)
        like = f"%{keyword}%"
        terms = _expand_search_terms(keyword)
        stmt = stmt.where(
            or_(
                models.CatalogTable.table_name.ilike(like),
                models.CatalogTable.description.ilike(like),
                *[
                    or_(
                        models.CatalogTable.table_name.ilike(f"%{t}%"),
                        models.CatalogTable.description.ilike(f"%{t}%"),
                    )
                    for t in terms
                ],
            )
        )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# 中文业务词 -> 常见英文表名列名 (帮助 LLM 中文检索命中英文表名)
_TABLE_SYNONYMS: dict[str, list[str]] = {
    "订单": ["order", "orders", "sales"],
    "销售": ["sales", "sale", "revenue", "order"],
    "用户": ["user", "users", "customer", "customers", "member"],
    "客户": ["customer", "customers", "user", "users"],
    "产品": ["product", "products", "sku", "item"],
    "商品": ["product", "products", "sku", "item"],
    "成本": ["cost", "costs"],
    "库存": ["stock", "inventory", "warehouse"],
    "毛利": ["margin", "gross", "profit"],
    "收入": ["revenue", "income", "sales"],
    "员工": ["employee", "employees", "staff"],
    "部门": ["dept", "department", "org"],
    "区域": ["region", "area", "zone"],
}


def _expand_search_terms(keyword: str) -> list[str]:
    """把检索词扩展为同义候选: 原文 + 中英映射词."""
    terms: list[str] = []
    for zh, en_list in _TABLE_SYNONYMS.items():
        if zh in keyword:
            terms.extend(en_list)
    # 关键词按分隔符拆分, 保留长度>=2的片段 (如 "分析订单数据" -> 订单/数据)
    import re

    for seg in re.split(r"[\s,、;；]+|分析|参考|说明|计算|给出", keyword):  # noqa: RUF001  全角分隔符按中文习惯保留
        seg = seg.strip()
        if 1 < len(seg) <= 12:
            terms.append(seg)
    # 去重保序
    seen: set[str] = set()
    result = []
    for t in terms:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result


async def get_table(session: AsyncSession, table_id: int) -> models.CatalogTable:
    table = await session.get(models.CatalogTable, table_id)
    if table is None:
        raise NotFoundError(f"目录表不存在: {table_id}")
    return table


async def search_columns(
    session: AsyncSession, keyword: str, limit: int = 50, tenant: str = "default"
) -> list[models.CatalogColumn]:
    like = f"%{keyword}%"
    # M6 多租户: 仅检索本租户数据源下的列 (经目录表关联)
    tenant_tables = select(models.CatalogTable.id).where(
        models.CatalogTable.source_id.in_(
            select(models.DataSource.id).where(models.DataSource.tenant_id == tenant)
        )
    )
    stmt = (
        select(models.CatalogColumn)
        .where(
            models.CatalogColumn.column_name.ilike(like),
            models.CatalogColumn.table_id.in_(tenant_tables),
        )
        .order_by(models.CatalogColumn.column_name)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def catalog_stats(session: AsyncSession, tenant: str = "default") -> dict:
    """目录总览统计 (按租户隔离), 供数据资产门户首页展示."""
    tenant_sources = select(models.DataSource.id).where(models.DataSource.tenant_id == tenant)
    tenant_tables = select(models.CatalogTable.id).where(models.CatalogTable.source_id.in_(tenant_sources))
    sources = await session.scalar(
        select(func.count(models.DataSource.id)).where(models.DataSource.tenant_id == tenant)
    ) or 0
    tables = await session.scalar(
        select(func.count(models.CatalogTable.id)).where(models.CatalogTable.source_id.in_(tenant_sources))
    ) or 0
    columns = await session.scalar(
        select(func.count(models.CatalogColumn.id)).where(models.CatalogColumn.table_id.in_(tenant_tables))
    ) or 0
    runs = await session.scalar(
        select(func.count(models.IngestionRun.id)).where(models.IngestionRun.source_id.in_(tenant_sources))
    ) or 0
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
    from app.security.acl import apply_column_acl, denied_columns
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

    # 列级权限 (M5): 按角色剔除禁止列
    denied = await denied_columns(session, role or "viewer", table.id)
    masked_rows = apply_column_acl(masked_rows, denied)

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
