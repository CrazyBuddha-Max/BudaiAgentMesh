"""向量检索: 可插拔向量后端 (M6-1: pgvector / Milvus 适配).

后端契约 `VectorBackend` 只管"查询向量 -> Top-K 命中", 业务入口 `retrieve()`
签名保持不变, 内部按配置自动选择实现:

- BruteForceBackend: 全量余弦排序 (默认, SQLite/演示环境, M2 起步实现)
- PgVectorBackend : PostgreSQL pgvector 扩展 (`<=>` 余弦距离, SQL 端排序)
- MilvusBackend   : Milvus 向量库 (可选依赖 pymilvus, 懒加载)

三者共享同一 RetrieveHit 契约, 上层业务代码无需感知差异.
"""
import asyncio
import importlib.util
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BizError
from app.knowledge.embeddings import Embedder, get_embedder
from app.knowledge.models import KnowledgeChunk

_EMBEDDING_DIM = 768  # 与 HashEmbedder 对齐; 生产按实际 embedding 提供方维度覆盖


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


class VectorBackend(ABC):
    """向量后端契约: 输入查询向量, 输出 Top-K 命中."""

    name: str = "base"

    @abstractmethod
    async def retrieve(
        self,
        session: AsyncSession,
        query_vec: list[float],
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[RetrieveHit]:
        """按向量检索, 结果按相关度降序."""


class BruteForceBackend(VectorBackend):
    """全量余弦暴力检索: 零依赖兜底, 适合 SQLite / 演示 / 小规模数据."""

    name = "brute_force"

    async def retrieve(
        self,
        session: AsyncSession,
        query_vec: list[float],
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[RetrieveHit]:
        rows = await session.execute(select(KnowledgeChunk).where(KnowledgeChunk.embedding.is_not(None)))
        hits: list[RetrieveHit] = []
        for chunk in rows.scalars():
            if not chunk.embedding:
                continue
            score = cosine(query_vec, chunk.embedding)
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


class PgVectorBackend(VectorBackend):
    """PostgreSQL pgvector: embedding 列动态 cast 为 vector, `<=>` 余弦距离 SQL 端排序.

    采用 `embedding::text::vector` 方案: 复用现有 JSON 列, 无需改表结构即可在
    PostgreSQL 上享受 pgvector 索引加速; 非 PG 方言调用时抛 BizError 引导降级.
    """

    name = "pgvector"

    @staticmethod
    def build_query_sql() -> str:
        """构造 pgvector 检索 SQL (独立成方法便于单元测试)."""
        return """
            SELECT id, doc_id, content, meta,
                   1 - (embedding::text::vector <=> CAST(:qv AS vector)) AS score
            FROM knowledge_chunks
            WHERE embedding IS NOT NULL
              AND 1 - (embedding::text::vector <=> CAST(:qv AS vector)) >= :min_score
            ORDER BY embedding::text::vector <=> CAST(:qv AS vector)
            LIMIT :top_k
        """

    @staticmethod
    def _vector_literal(query_vec: list[float]) -> str:
        return "[" + ",".join(repr(v) for v in query_vec) + "]"

    @staticmethod
    def _is_postgres(session: AsyncSession) -> bool:
        bind = getattr(session, "bind", None)
        return bind is not None and getattr(bind, "dialect", None) is not None and bind.dialect.name == "postgresql"

    async def retrieve(
        self,
        session: AsyncSession,
        query_vec: list[float],
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[RetrieveHit]:
        if not self._is_postgres(session):
            raise BizError(
                "PgVectorBackend 需要 PostgreSQL 数据库 (database_url 指向 pg 且已启用 pgvector); "
                "SQLite 环境请使用默认 brute_force 后端"
            )
        rows = await session.execute(
            text(self.build_query_sql()),
            {"qv": self._vector_literal(query_vec), "top_k": top_k, "min_score": min_score},
        )
        return [
            RetrieveHit(
                chunk_id=row.id,
                doc_id=row.doc_id,
                content=row.content,
                score=round(row.score, 4),
                metadata=row.meta,
            )
            for row in rows
        ]


class MilvusBackend(VectorBackend):
    """Milvus 向量库: collection 即检索域, 可选依赖 pymilvus (懒加载).

    数据同步 (upsert/delete) 由集成方调用本类维护; 检索直接返回 Milvus 命中.
    未安装 pymilvus 时构造即抛 BizError, 引导安装而非静默失败.
    """

    name = "milvus"

    def __init__(self, uri: str | None = None, dim: int | None = None) -> None:
        if importlib.util.find_spec("pymilvus") is None:
            raise BizError("使用 Milvus 后端需安装 pymilvus (pip install pymilvus)")
        from pymilvus import MilvusClient

        self._client = MilvusClient(uri=uri or settings.milvus_uri or "./data/budai_milvus.db")
        self._collection = "knowledge_chunks"
        self.dim = dim or _EMBEDDING_DIM

    def _ensure_collection(self) -> None:
        """幂等建集合: chunk_id/doc_id/content 标量 + embedding 向量."""
        from pymilvus import DataType

        if self._client.has_collection(self._collection):
            return
        schema = self._client.create_schema(auto_id=True, enable_dynamic_field=True)
        schema.add_field("pk", DataType.INT64, is_primary=True)
        schema.add_field("chunk_id", DataType.INT64)
        schema.add_field("doc_id", DataType.INT64)
        schema.add_field("content", DataType.VARCHAR, max_length=65535)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=self.dim)
        self._client.create_collection(collection_name=self._collection, schema=schema)

    def upsert(self, chunk_id: int, doc_id: int, content: str, embedding: list[float]) -> None:
        """写入/更新单个切块 (由知识入库流程在 ingest 时调用)."""
        self._ensure_collection()
        self._client.upsert(
            collection_name=self._collection,
            data=[{"chunk_id": chunk_id, "doc_id": doc_id, "content": content, "embedding": embedding}],
        )

    def delete_by_chunk(self, chunk_id: int) -> None:
        """按切块删除 (由知识删除流程调用)."""
        if self._client.has_collection(self._collection):
            self._client.delete(collection_name=self._collection, filter=f"chunk_id == {chunk_id}")

    async def retrieve(
        self,
        session: AsyncSession,
        query_vec: list[float],
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[RetrieveHit]:
        self._ensure_collection()
        # Milvus 客户端为同步实现, 放入线程池避免阻塞事件循环
        res = await asyncio.to_thread(
            self._client.search,
            collection_name=self._collection,
            data=[query_vec],
            limit=top_k,
            output_fields=["chunk_id", "doc_id", "content"],
            search_params={"metric_type": "COSINE", "params": {"nprobe": 10}},
        )
        hits: list[RetrieveHit] = []
        for row in res[0]:
            score = float(row["distance"])
            if score < min_score:
                continue
            hits.append(
                RetrieveHit(
                    chunk_id=int(row["entity"]["chunk_id"]),
                    doc_id=int(row["entity"]["doc_id"]),
                    content=row["entity"]["content"],
                    score=round(score, 4),
                    metadata=None,
                )
            )
        return hits


def get_backend() -> VectorBackend:
    """按配置选择向量后端: 显式模式优先, auto 按数据库方言自动决定."""
    mode = (settings.vector_backend or "auto").lower()
    if mode == "brute_force":
        return BruteForceBackend()
    if mode == "pgvector":
        return PgVectorBackend()
    if mode == "milvus":
        return MilvusBackend()
    # auto: PostgreSQL 优先 pgvector, 其余回退全量余弦
    if settings.database_url and settings.database_url.startswith(("postgres", "postgresql")):
        return PgVectorBackend()
    return BruteForceBackend()


async def retrieve(
    session: AsyncSession,
    query: str,
    top_k: int = 5,
    embedder: Embedder | None = None,
    min_score: float = 0.0,
) -> list[RetrieveHit]:
    """语义检索 (兼容入口): 查询向量化 -> 按配置后端检索 -> Top-K.

    签名自 M2 起保持稳定, 后端切换 (pgvector/Milvus) 对调用方透明.
    """
    embedder = embedder or get_embedder()
    query_vec = embedder.embed(query)
    backend = get_backend()
    return await backend.retrieve(session, query_vec, top_k=top_k, min_score=min_score)
