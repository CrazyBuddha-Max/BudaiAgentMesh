"""知识服务: 文档入库 / 目录管理 / 语义检索 (RAG 流水线编排)."""
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizError, NotFoundError
from app.core.logging import get_logger
from app.knowledge.chunking import chunk_text, count_tokens
from app.knowledge.embeddings import get_embedder
from app.knowledge.models import KnowledgeChunk, KnowledgeDoc
from app.knowledge.parsers import extract_text, guess_source_type
from app.knowledge.vectorstore import RetrieveHit, retrieve

logger = get_logger(__name__)
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "uploads")


async def ingest_document(
    session: AsyncSession,
    file_name: str,
    raw: bytes,
    title: str | None = None,
    embedder=None,
    tenant: str = "default",
) -> KnowledgeDoc:
    """解析 -> 切分 -> 向量化 -> 入库, 失败时保留失败记录供排查."""
    doc = KnowledgeDoc(
        title=title or os.path.splitext(file_name)[0],
        tenant_id=tenant,
        source_type=guess_source_type(file_name),
        file_name=file_name,
        file_size=len(raw),
        status="processing",
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)

    try:
        from app.core.telemetry import span

        async with span("knowledge.ingest", doc_id=doc.id, file=file_name):
            text = extract_text(file_name, raw)
            chunks = chunk_text(text)
            embedder = embedder or get_embedder()
            vectors = embedder.embed_batch(chunks)

            for index, (content, vec) in enumerate(zip(chunks, vectors)):
                session.add(
                    KnowledgeChunk(
                        doc_id=doc.id,
                        tenant_id=tenant,
                        chunk_index=index,
                        content=content,
                        token_count=count_tokens(content),
                        embedding=vec,
                        meta={"source": file_name, "chunk": index},
                    )
                )
            doc.chunk_count = len(chunks)
            doc.status = "ready"
            await session.commit()
    except Exception as exc:
        logger.exception("知识文档入库失败: %s", file_name)
        doc.status = "failed"
        doc.error = str(exc)
        await session.commit()
        raise BizError(f"文档解析失败: {exc}") from exc
    return doc


async def list_documents(session: AsyncSession, limit: int = 100, tenant: str = "default") -> list[KnowledgeDoc]:
    stmt = (
        select(KnowledgeDoc)
        .where(KnowledgeDoc.tenant_id == tenant)
        .order_by(KnowledgeDoc.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_document(session: AsyncSession, doc_id: int, tenant: str = "default") -> KnowledgeDoc:
    doc = await session.get(KnowledgeDoc, doc_id)
    if doc is None or doc.tenant_id != tenant:
        raise NotFoundError(f"知识文档不存在: {doc_id}")
    return doc


async def delete_document(session: AsyncSession, doc_id: int, tenant: str = "default") -> None:
    doc = await get_document(session, doc_id, tenant=tenant)
    await session.delete(doc)
    await session.commit()


async def search(
    session: AsyncSession,
    query: str,
    top_k: int = 5,
    tenant: str = "default",
) -> list[RetrieveHit]:
    return await retrieve(session, query, top_k=top_k, tenant=tenant)
