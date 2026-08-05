"""知识层 API: 文档管理 / 语义检索 / 指标语义层."""

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.knowledge.metrics_schemas import MetricCreate, MetricOut, MetricQueryRequest, MetricQueryResult
from app.knowledge.metrics_service import (
    create_metric,
    delete_metric,
    list_metrics,
    query_metric,
    to_out,
)
from app.knowledge.schemas import (
    DocDetailOut,
    KnowledgeDocOut,
    RetrieveHitOut,
    RetrieveRequest,
)
from app.knowledge.service import delete_document, get_document, ingest_document, list_documents, search
from app.security.auth import AnalystDep, CurrentUserDep

router = APIRouter()

SessionDep = Depends(get_session)


# ---------- 知识文档 ----------

@router.post("/documents", response_model=KnowledgeDocOut, status_code=201)
async def upload_document(
    user: AnalystDep,
    file: UploadFile = File(...),
    title: str = Form(default=""),
    session: AsyncSession = SessionDep,
):
    """上传知识文档 (txt/md/html/pdf), 自动解析切分向量化入库."""
    raw = await file.read()
    return await ingest_document(session, file.filename or "untitled", raw, title or None)


@router.get("/documents", response_model=list[KnowledgeDocOut])
async def documents(
    user: CurrentUserDep,
    limit: int = Query(100, le=500),
    session: AsyncSession = SessionDep,
):
    return await list_documents(session, limit)


@router.get("/documents/{doc_id}", response_model=DocDetailOut)
async def document_detail(
    doc_id: int,
    user: CurrentUserDep,
    session: AsyncSession = SessionDep,
):
    return await get_document(session, doc_id)


@router.delete("/documents/{doc_id}", status_code=204)
async def remove_document(
    doc_id: int,
    user: AnalystDep,
    session: AsyncSession = SessionDep,
):
    await delete_document(session, doc_id)


@router.post("/retrieve", response_model=list[RetrieveHitOut])
async def retrieve_knowledge(
    payload: RetrieveRequest,
    user: CurrentUserDep,
    session: AsyncSession = SessionDep,
):
    """语义检索: 返回与查询最相关的知识切块 (RAG 检索环节)."""
    hits = await search(session, payload.query, top_k=payload.top_k)
    return [RetrieveHitOut(**hit.__dict__) for hit in hits]


# ---------- 指标语义层 ----------

@router.get("/metrics", response_model=list[MetricOut])
async def metrics(
    user: CurrentUserDep,
    keyword: str | None = None,
    status: str | None = None,
    limit: int = Query(200, le=500),
    session: AsyncSession = SessionDep,
):
    """指标目录: 统一口径定义列表."""
    items = await list_metrics(session, keyword, status, limit)
    return [await to_out(session, m) for m in items]


@router.post("/metrics", response_model=MetricOut, status_code=201)
async def create_metric_endpoint(
    payload: MetricCreate, user: AnalystDep, session: AsyncSession = SessionDep
):
    """新建指标: 绑定目录表, 度量表达式必须引用已注册列."""
    metric = await create_metric(session, payload)
    return await to_out(session, metric)


@router.delete("/metrics/{metric_id}", status_code=204)
async def remove_metric(
    metric_id: int, user: AnalystDep, session: AsyncSession = SessionDep
) -> None:
    await delete_metric(session, metric_id)


@router.post("/metrics/{metric_id}/query", response_model=MetricQueryResult)
async def run_metric_query(
    metric_id: int,
    payload: MetricQueryRequest,
    user: AnalystDep,
    session: AsyncSession = SessionDep,
):
    """执行指标查询: 返回口径正确的数字 + 可追溯的定义."""
    return await query_metric(session, metric_id, payload)
