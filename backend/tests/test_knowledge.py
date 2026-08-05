"""知识层测试: 切分 / 向量化 / 检索 / API 全链路."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.knowledge.chunking import chunk_text, count_tokens
from app.knowledge.embeddings import HashEmbedder
from app.knowledge.vectorstore import cosine
from app.main import app


async def _client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def _login(client: AsyncClient) -> str:
    resp = await client.post("/api/security/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------- 单元: 切分 ----------

def test_chunk_text_short_stays_single():
    assert chunk_text("短文本") == ["短文本"]


def test_chunk_text_long_splits_with_overlap():
    text = "段甲" * 300 + "\n\n" + "段乙" * 300
    chunks = chunk_text(text, chunk_size=200, overlap=50)
    assert len(chunks) >= 2
    assert len(chunks[-1]) <= 260


def test_count_tokens():
    assert count_tokens("毛利率等于收入减成本") > 0


# ---------- 单元: 向量化 ----------

def test_hash_embedding_deterministic():
    emb = HashEmbedder()
    a = emb.embed("毛利率口径说明")
    b = emb.embed("毛利率口径说明")
    assert a == b
    assert len(a) == emb.dim


def test_cosine_similarity():
    emb = HashEmbedder()
    same = cosine(emb.embed("智能音箱价格"), emb.embed("智能音箱价格"))
    diff = cosine(emb.embed("智能音箱价格"), emb.embed("复购率计算方式"))
    assert same > diff


# ---------- 集成: 检索 ----------

@pytest.mark.anyio
async def test_retrieve_end_to_end():
    async with await _client() as client:
        token = await _login(client)
        headers = _auth(token)

        doc_a = "毛利率等于收入减成本除以收入。智能音箱客单价约 299 元。".encode()
        doc_b = "复购率等于复购客户数除以活跃客户数。".encode()
        resp = await client.post(
            "/api/knowledge/documents",
            headers=headers,
            data={"title": "指标口径"},
            files=[("file", ("metrics.txt", doc_a, "text/plain"))],
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["status"] == "ready"

        resp = await client.post(
            "/api/knowledge/documents",
            headers=headers,
            data={"title": "复购定义"},
            files=[("file", ("repeat.txt", doc_b, "text/plain"))],
        )
        assert resp.status_code == 201, resp.text

        resp = await client.get("/api/knowledge/documents", headers=headers)
        docs = resp.json()
        assert len(docs) >= 2
        assert all(d["status"] == "ready" for d in docs)

        resp = await client.post(
            "/api/knowledge/retrieve", headers=headers, json={"query": "智能音箱价格", "top_k": 3}
        )
        assert resp.status_code == 200
        hits = resp.json()
        assert len(hits) >= 1
        assert hits[0]["score"] >= 0
        assert "智能音箱" in hits[0]["content"]

        resp = await client.delete(f"/api/knowledge/documents/{docs[0]['id']}", headers=headers)
        assert resp.status_code == 204
