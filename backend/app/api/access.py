"""接入层 API: 数据源 / 采集 / 目录浏览."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import models
from app.access.catalog import (
    catalog_stats,
    create_source,
    delete_source,
    get_source,
    get_table,
    list_sources,
    list_tables,
    search_columns,
    update_source,
)
from app.access.connectors import registry
from app.access.ingestion import ingest_source, test_source
from app.access.schemas import (
    ColumnOut,
    ConnectorInfo,
    IngestResult,
    SourceCreate,
    SourceOut,
    SourceUpdate,
    TableOut,
)
from app.core.database import get_session
from app.security.auth import AnalystDep, CurrentUserDep

router = APIRouter()

SessionDep = Depends(get_session)

_CONNECTOR_META = {
    "postgres": ("PostgreSQL", "关系型数据库, 实时增量 (CDC) 规划中 (M5)"),
    "mysql": ("MySQL", "关系型数据库, 实时增量 (CDC) 规划中 (M5)"),
    "csv": ("CSV 文件", "本地结构化文件, 适合快速接入与演示"),
}


# ---------- 数据源 ----------

@router.get("/sources", response_model=list[SourceOut])
async def sources(
    user: CurrentUserDep,
    session: AsyncSession = SessionDep,
) -> list[models.DataSource]:
    return await list_sources(session)


@router.post("/sources", response_model=SourceOut, status_code=201)
async def create(
    payload: SourceCreate,
    user: AnalystDep,
    session: AsyncSession = SessionDep,
) -> models.DataSource:
    return await create_source(session, payload)


@router.get("/sources/{source_id}", response_model=SourceOut)
async def source_detail(
    source_id: int,
    user: CurrentUserDep,
    session: AsyncSession = SessionDep,
) -> models.DataSource:
    return await get_source(session, source_id)


@router.patch("/sources/{source_id}", response_model=SourceOut)
async def patch_source(
    source_id: int,
    payload: SourceUpdate,
    user: AnalystDep,
    session: AsyncSession = SessionDep,
) -> models.DataSource:
    return await update_source(session, source_id, payload)


@router.delete("/sources/{source_id}", status_code=204)
async def remove(
    source_id: int,
    user: AnalystDep,
    session: AsyncSession = SessionDep,
) -> None:
    await delete_source(session, source_id)


# ---------- 连接与采集 ----------

@router.post("/sources/{source_id}/test")
async def test_connection(
    source_id: int,
    user: AnalystDep,
    session: AsyncSession = SessionDep,
) -> dict:
    message = await test_source(session, source_id)
    return {"source_id": source_id, "status": "active", "message": message}


@router.post("/sources/{source_id}/ingest", response_model=IngestResult)
async def run_ingest(
    source_id: int,
    user: AnalystDep,
    session: AsyncSession = SessionDep,
) -> IngestResult:
    run = await ingest_source(session, source_id)
    return IngestResult(
        source_id=source_id,
        run_id=run.id,
        status=run.status,
        tables_found=run.tables_found,
        message=run.message or "",
    )


# ---------- 连接器市场 ----------

@router.get("/connectors", response_model=list[ConnectorInfo])
async def connectors(user: CurrentUserDep) -> list[ConnectorInfo]:
    available = registry.available()
    result = []
    for ctype in available:
        display, desc = _CONNECTOR_META.get(ctype, (ctype, ""))
        cls = registry.get(ctype)
        result.append(
            ConnectorInfo(type=ctype, display_name=display, description=desc, available=True, params=list(cls.__init__.__annotations__))
        )
    return result


# ---------- 元数据目录 ----------

@router.get("/catalog/stats")
async def stats(user: CurrentUserDep, session: AsyncSession = SessionDep) -> dict:
    return await catalog_stats(session)


@router.get("/catalog/tables", response_model=list[TableOut])
async def tables(
    user: CurrentUserDep,
    source_id: int | None = None,
    keyword: str | None = None,
    limit: int = Query(100, le=500),
    session: AsyncSession = SessionDep,
) -> list[models.CatalogTable]:
    return await list_tables(session, source_id=source_id, keyword=keyword, limit=limit)


@router.get("/catalog/tables/{table_id}", response_model=TableOut)
async def table_detail(
    table_id: int,
    user: CurrentUserDep,
    session: AsyncSession = SessionDep,
) -> models.CatalogTable:
    return await get_table(session, table_id)


@router.get("/catalog/columns", response_model=list[ColumnOut])
async def columns(
    user: CurrentUserDep,
    keyword: str = Query(..., min_length=1),
    limit: int = Query(50, le=200),
    session: AsyncSession = SessionDep,
) -> list[models.CatalogColumn]:
    return await search_columns(session, keyword, limit)
