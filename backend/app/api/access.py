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
from app.security.auth import AdminDep, AnalystDep, CurrentUserDep

router = APIRouter()

SessionDep = Depends(get_session)

_CONNECTOR_META = {
    "postgres": ("PostgreSQL", "关系型数据库, 支持增量指纹检测 (M6)"),
    "mysql": ("MySQL", "关系型数据库, 支持增量指纹检测 (M6)"),
    "csv": ("CSV 文件", "本地结构化文件, 指纹增量 (M6)"),
}


# ---------- 数据源 ----------

@router.get("/sources", response_model=list[SourceOut])
async def sources(
    user: CurrentUserDep,
    session: AsyncSession = SessionDep,
) -> list[models.DataSource]:
    return await list_sources(session, tenant=user.tenant)


@router.post("/sources", response_model=SourceOut, status_code=201)
async def create(
    payload: SourceCreate,
    user: AnalystDep,
    session: AsyncSession = SessionDep,
) -> models.DataSource:
    return await create_source(session, payload, tenant=user.tenant)


@router.get("/sources/{source_id}", response_model=SourceOut)
async def source_detail(
    source_id: int,
    user: CurrentUserDep,
    session: AsyncSession = SessionDep,
) -> models.DataSource:
    return await get_source(session, source_id, tenant=user.tenant)


@router.patch("/sources/{source_id}", response_model=SourceOut)
async def patch_source(
    source_id: int,
    payload: SourceUpdate,
    user: AnalystDep,
    session: AsyncSession = SessionDep,
) -> models.DataSource:
    return await update_source(session, source_id, payload, tenant=user.tenant)


@router.delete("/sources/{source_id}", status_code=204)
async def remove(
    source_id: int,
    user: AnalystDep,
    session: AsyncSession = SessionDep,
) -> None:
    await delete_source(session, source_id, tenant=user.tenant)


# ---------- 连接与采集 ----------

@router.post("/sources/{source_id}/test")
async def test_connection(
    source_id: int,
    user: AnalystDep,
    session: AsyncSession = SessionDep,
) -> dict:
    message = await test_source(session, source_id, tenant=user.tenant)
    return {"source_id": source_id, "status": "active", "message": message}


@router.post("/sources/{source_id}/ingest", response_model=IngestResult)
async def run_ingest(
    source_id: int,
    user: AnalystDep,
    session: AsyncSession = SessionDep,
) -> IngestResult:
    run = await ingest_source(session, source_id, tenant=user.tenant)
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
    return await catalog_stats(session, tenant=user.tenant)


@router.get("/catalog/tables", response_model=list[TableOut])
async def tables(
    user: CurrentUserDep,
    source_id: int | None = None,
    keyword: str | None = None,
    limit: int = Query(100, le=500),
    session: AsyncSession = SessionDep,
) -> list[models.CatalogTable]:
    return await list_tables(session, source_id=source_id, keyword=keyword, limit=limit, tenant=user.tenant)


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
    return await search_columns(session, keyword, limit, tenant=user.tenant)


# ---------- 联邦接入 (M6) ----------

@router.get("/federation/peers")
async def federation_peers(user: AdminDep, session: AsyncSession = SessionDep) -> list[dict]:
    """联邦对等实例列表 (admin)."""
    from app.access.federated import list_peers

    rows = await list_peers(session)
    return [
        {"id": p.id, "name": p.name, "base_url": p.base_url, "status": p.status, "created_at": p.created_at.isoformat()}
        for p in rows
    ]


@router.post("/federation/peers", status_code=201)
async def federation_create_peer(
    payload: dict, user: AdminDep, session: AsyncSession = SessionDep
) -> dict:
    """注册联邦实例 (admin): {name, base_url, api_token?}."""
    from app.access.federated import create_peer

    peer = await create_peer(
        session,
        name=payload.get("name", ""),
        base_url=payload.get("base_url", ""),
        api_token=payload.get("api_token"),
    )
    return {"id": peer.id, "name": peer.name, "base_url": peer.base_url, "status": peer.status}


@router.patch("/federation/peers/{peer_id}")
async def federation_patch_peer(
    peer_id: int, payload: dict, user: AdminDep, session: AsyncSession = SessionDep
) -> dict:
    """更新联邦实例状态 (admin)."""
    from app.access.federated import set_peer_status

    peer = await set_peer_status(session, peer_id, payload.get("status", "active"))
    return {"id": peer.id, "name": peer.name, "base_url": peer.base_url, "status": peer.status}


@router.delete("/federation/peers/{peer_id}", status_code=204)
async def federation_delete_peer(
    peer_id: int, user: AdminDep, session: AsyncSession = SessionDep
) -> None:
    """移除联邦实例 (admin)."""
    from app.access.federated import delete_peer

    await delete_peer(session, peer_id)


@router.get("/federation/search")
async def federation_search(
    user: CurrentUserDep,
    keyword: str | None = None,
    limit: int = Query(20, le=100),
    session: AsyncSession = SessionDep,
) -> list[dict]:
    """联邦目录检索: 并发透传全部启用实例的 catalog/tables."""
    from app.access.federated import federated_search

    return await federated_search(session, keyword=keyword, limit=limit)


@router.get("/federation/peers/{peer_id}/query")
async def federation_query(
    peer_id: int,
    user: CurrentUserDep,
    path: str = Query("/api/access/catalog/tables"),
    keyword: str | None = None,
    limit: int = Query(20, le=100),
    session: AsyncSession = SessionDep,
) -> dict:
    """对指定实例透传查询 (默认远端目录表; 可自定义 path 与关键字)."""
    from app.access.federated import federated_query

    params = {"keyword": keyword, "limit": limit} if keyword else None
    return await federated_query(session, peer_id, path, params=params)
