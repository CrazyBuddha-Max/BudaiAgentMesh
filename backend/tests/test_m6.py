"""M6 测试: 可插拔向量后端 (pgvector / Milvus 适配)."""
import importlib.util

import pytest

from app.core.config import settings
from app.knowledge.vectorstore import (
    BruteForceBackend,
    MilvusBackend,
    PgVectorBackend,
    VectorBackend,
    get_backend,
    retrieve,
)

# ---------- 后端工厂 ----------

def test_backend_explicit_bruteforce(monkeypatch):
    monkeypatch.setattr(settings, "vector_backend", "brute_force")
    assert isinstance(get_backend(), BruteForceBackend)


def test_backend_explicit_pgvector(monkeypatch):
    monkeypatch.setattr(settings, "vector_backend", "pgvector")
    assert isinstance(get_backend(), PgVectorBackend)


def test_backend_auto_sqlite_falls_back_to_bruteforce(monkeypatch):
    monkeypatch.setattr(settings, "vector_backend", "auto")
    monkeypatch.setattr(settings, "database_url", "")  # 测试环境为 SQLite
    assert isinstance(get_backend(), BruteForceBackend)


def test_backend_auto_postgres_url_picks_pgvector(monkeypatch):
    monkeypatch.setattr(settings, "vector_backend", "auto")
    monkeypatch.setattr(settings, "database_url", "postgresql+asyncpg://user:pass@localhost:5432/db")
    assert isinstance(get_backend(), PgVectorBackend)


def test_backend_unknown_mode_falls_back_to_auto(monkeypatch):
    monkeypatch.setattr(settings, "vector_backend", "weird-mode")
    monkeypatch.setattr(settings, "database_url", "")
    assert isinstance(get_backend(), BruteForceBackend)


# ---------- pgvector 后端 ----------

def test_pgvector_sql_shape():
    sql = PgVectorBackend.build_query_sql()
    assert "<=>" in sql                      # 余弦距离操作符
    assert "ORDER BY" in sql and "LIMIT :top_k" in sql
    assert ":min_score" in sql and ":qv" in sql


def test_pgvector_vector_literal():
    assert PgVectorBackend._vector_literal([0.5, -1.0, 2.0]) == "[0.5,-1.0,2.0]"


def test_pgvector_guard_on_sqlite(monkeypatch):
    """非 PostgreSQL 方言上调用 pgvector 后端应抛 BizError 引导降级."""
    monkeypatch.setattr(settings, "vector_backend", "pgvector")
    backend = get_backend()


    class FakeSession:
        bind = None  # 模拟 SQLite 引擎无 PG 方言

    with pytest.raises(Exception) as exc_info:
        import asyncio

        asyncio.run(backend.retrieve(FakeSession(), [0.1, 0.2], top_k=2))  # type: ignore[arg-type]
    assert "PostgreSQL" in str(exc_info.value)


# ---------- Milvus 后端 ----------

def test_milvus_missing_dependency_raises_bizerror(monkeypatch):
    """未安装 pymilvus 时构造 Milvus 后端应抛业务异常引导安装."""
    monkeypatch.setattr(importlib.util, "find_spec", lambda _name: None)
    monkeypatch.setattr(settings, "milvus_uri", "http://localhost:19530")
    with pytest.raises(Exception) as exc_info:
        MilvusBackend()
    assert "pymilvus" in str(exc_info.value)


@pytest.mark.skipif(
    importlib.util.find_spec("pymilvus") is None, reason="pymilvus 未安装"
)
def test_milvus_backend_constructible():
    backend = MilvusBackend(uri="./data/test_budai_milvus.db", dim=8)
    assert isinstance(backend, VectorBackend)
    assert backend.name == "milvus"
    assert backend.dim == 8


# ---------- 兼容回归: retrieve() 入口签名不变 ----------

async def test_retrieve_bruteforce_roundtrip(monkeypatch):
    """端到端: 默认后端 (SQLite/brute_force) 检索链路保持可用."""
    from app.core.database import SessionLocal
    from app.knowledge.models import KnowledgeChunk

    monkeypatch.setattr(settings, "vector_backend", "brute_force")
    async with SessionLocal() as session:
        chunk = KnowledgeChunk(
            doc_id=1, chunk_index=0, content="智能音箱价格亲民", token_count=8,
            embedding=[0.1, 0.2, 0.3], meta={"source": "test"},
        )
        session.add(chunk)
        await session.commit()

        hits = await retrieve(session, "智能音箱价格", top_k=5)
        assert isinstance(hits, list)
        # 至少命中写入的切块 (相似度 > 0)
        assert any(h.content == "智能音箱价格亲民" for h in hits)
