"""M6 测试: 可插拔向量后端 / 增量采集 (CDC 简化) / SSO OAuth2.0 登录."""
import importlib.util
import os
import shutil
import tempfile

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.knowledge.vectorstore import (
    BruteForceBackend,
    MilvusBackend,
    PgVectorBackend,
    VectorBackend,
    get_backend,
    retrieve,
)
from app.main import app

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


async def _client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def _login(client: AsyncClient, username: str = "admin", password: str = "admin123") -> str:
    resp = await client.post(
        "/api/security/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------- 增量采集 (M6) ----------

# ---------- 增量采集 ----------


@pytest.mark.anyio
async def test_incremental_ingest_csv():
    """CSV 增量: 首次全量 -> 无变化跳过 -> 文件变更后重采并更新目录行数."""
    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, "incr.csv")
    with open(path, "w", encoding="utf-8") as f:
        f.write("id,region,amount\n1,east,10\n2,west,20\n")

    try:
        async with await _client() as client:
            token = await _login(client)
            resp = await client.post(
                "/api/access/sources",
                json={
                    "name": "增量测试源",
                    "source_type": "csv",
                    "description": None,
                    "host": None,
                    "port": None,
                    "database": None,
                    "schema_name": "public",
                    "username": None,
                    "password": None,
                    "file_path": path,
                },
                headers=_auth(token),
            )
            assert resp.status_code == 201, resp.text
            sid = resp.json()["id"]

            # 首次采集: 全量
            r1 = await client.post(f"/api/access/sources/{sid}/ingest", headers=_auth(token))
            assert r1.status_code == 200, r1.text
            body1 = r1.json()
            assert body1["status"] == "success"
            assert body1["tables_found"] == 1

            # 再次采集: 无变化 -> 增量跳过
            r2 = await client.post(f"/api/access/sources/{sid}/ingest", headers=_auth(token))
            body2 = r2.json()
            assert body2["status"] == "success"
            assert body2["tables_found"] == 0
            assert ("增量" in body2["message"]) or ("无变化" in body2["message"])

            # 修改文件 -> 触发重采
            with open(path, "a", encoding="utf-8") as f:
                f.write("3,south,30\n")
            r3 = await client.post(f"/api/access/sources/{sid}/ingest", headers=_auth(token))
            body3 = r3.json()
            assert body3["status"] == "success"
            assert body3["tables_found"] == 1

            # 目录行数已更新为 3
            resp = await client.get("/api/access/catalog/tables", headers=_auth(token))
            assert resp.status_code == 200, resp.text
            hit = [t for t in resp.json() if t["source_id"] == sid]
            assert hit and hit[0]["row_count"] == 3
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------- SSO / OAuth2.0 ----------


def _sso_config_dict() -> dict:
    """测试用 SSO 配置 (指向内存 mock 提供方)."""
    return {
        "provider_name": "MockSSO",
        "client_id": "test-client",
        "client_secret": "test-secret",
        "authorize_url": "http://mock/auth",
        "token_url": "http://mock/token",
        "userinfo_url": "http://mock/userinfo",
        "scope": "openid profile",
        "role_claim": "role",
        "default_role": "viewer",
        "redirect_uri": "http://localhost:5173/login",
    }


@pytest.mark.anyio
async def test_sso_endpoint_flow(monkeypatch):
    """SSO 端点链路: config -> 回跳 callback (state 校验 + 换码 + JWT) -> /me 可用."""
    from app.security.sso import SSO_PROVIDER

    monkeypatch.setattr(SSO_PROVIDER, "enabled", True)
    monkeypatch.setattr(SSO_PROVIDER, "config", _sso_config_dict())
    monkeypatch.setattr(SSO_PROVIDER, "exchange_code", _fake_exchange)

    async with await _client() as client:
        # 1. 获取 SSO 配置
        resp = await client.get("/api/security/sso/config")
        assert resp.status_code == 200, resp.text
        cfg = resp.json()
        assert cfg["enabled"] is True
        assert cfg["name"] == "MockSSO"
        assert cfg.get("authorize_url")

        # 2. state 校验失败 -> 拒绝
        resp_bad = await client.get("/api/security/sso/callback?code=x&state=unknown-state")
        assert resp_bad.status_code in (400, 401), resp_bad.text

        # 3. 正常回跳: 先由 authorize_url 产生合法 state
        import re

        state = re.search(r"state=([^&]+)", cfg["authorize_url"]).group(1)
        resp2 = await client.get(f"/api/security/sso/callback?code=mock-code&state={state}")
        assert resp2.status_code == 200, resp2.text
        data = resp2.json()
        assert data["access_token"]
        assert data["user"]["username"] == "mockuser"

        # 4. SSO 签发的 JWT 可访问受保护接口
        resp3 = await client.get("/api/security/me", headers=_auth(data["access_token"]))
        assert resp3.status_code == 200, resp3.text
        assert resp3.json()["username"] == "mockuser"

        # 5. 未启用时返回 disabled
        monkeypatch.setattr(SSO_PROVIDER, "enabled", False)
        resp4 = await client.get("/api/security/sso/config")
        assert resp4.status_code == 200
        assert resp4.json()["enabled"] is False


async def _fake_exchange(code: str, client=None):
    """测试桩: 绕过真实 HTTP, 直接返回映射用户."""
    from app.security.auth import CurrentUser

    return CurrentUser(username="mockuser", role="analyst")


@pytest.mark.anyio
async def test_sso_exchange_code_mapping(monkeypatch):
    """exchange_code 的 HTTP 链路: 换码 -> userinfo -> 角色映射 (MockTransport)."""
    import httpx

    from app.security.sso import SSO_PROVIDER

    monkeypatch.setattr(SSO_PROVIDER, "enabled", True)
    monkeypatch.setattr(SSO_PROVIDER, "config", _sso_config_dict())

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "tok-1", "token_type": "Bearer"})
        if request.url.path == "/userinfo":
            return httpx.Response(
                200,
                json={
                    "sub": "u-1",
                    "preferred_username": "zhang.san",
                    "role": "admin",
                    "email": "zhang@corp.com",
                },
            )
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://mock") as client:
        user = await SSO_PROVIDER.exchange_code("the-code", client=client)
    assert user.username == "zhang.san"
    assert user.role == "admin"

    # 角色非法时回落默认角色
    def handler_no_role(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "tok-1"})
        return httpx.Response(200, json={"sub": "u-2", "preferred_username": "li.si", "role": "superuser"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler_no_role), base_url="http://mock") as client:
        user2 = await SSO_PROVIDER.exchange_code("c2", client=client)
    assert user2.username == "li.si"
    assert user2.role == "viewer"
