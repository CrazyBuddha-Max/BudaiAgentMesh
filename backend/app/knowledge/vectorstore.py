"""向量检索: 余弦相似度暴力检索 (M2 起步实现).

M5 将迁移至 pgvector / Milvus (接口保持, 仅换实现).
"""
import math
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.embeddings import Embedder, get_embedder
from app.knowledge.models import KnowledgeChunk


@dataclass
class RetrieveHit:
    chunk_id: int
    doc_id: int
    content: str
    score: float
    metadata: dict | None


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


async def retrieve(
    session: AsyncSession,
    query: str,
    top_k: int = 5,
    embedder: Embedder | None = None,
    min_score: float = 0.0,
) -> list[RetrieveHit]:
    """语义检索: 查询向量 -> 全量余弦排序 -> 返回 Top-K."""
    embedder = embedder or get_embedder()
    qv = embedder.embed(query)

    rows = await session.execute(select(KnowledgeChunk).where(KnowledgeChunk.embedding.is_not(None)))
    hits: list[RetrieveHit] = []
    for chunk in rows.scalars():
        if not chunk.embedding:
            continue
        score = cosine(qv, chunk.embedding)
        if score >= min_score:
            hits.append(
                RetrieveHit(
                    chunk_id=chunk.id,
                    doc_id=chunk.doc_id,
                    content=chunk.content,
                    score=round(score, 4),
                    metadata=chunk.meta,
                )
            )
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:top_k]
