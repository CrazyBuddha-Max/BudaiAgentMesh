"""M6 多租户 + 联邦接入测试."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app


async def _client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def _login(client: AsyncClient, username: str = "admin", password: str = "admin123") -> str:
    resp = await client.post("/api/security/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}

# ---------- 多租户隔离 (M6) ----------


async def _login_tenant(client: AsyncClient, username: str, password: str) -> str:
    resp = await client.post("/api/security/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.mark.anyio
async def test_tenant_data_isolation(monkeypatch, tmp_path):
    """租户 B 看不到租户 A 的数据源, 越权访问返回 404."""
    from app.security.auth import authenticate

    monkeypatch.setattr(
        settings,
        "builtin_users",
        "admin:admin123:admin,alice:alice123:analyst:tenant-a,bob:bob123:analyst:tenant-b",
    )
    # 确认解析: alice 归 tenant-a, bob 归 tenant-b
    assert authenticate("alice", "alice123").tenant == "tenant-a"
    assert authenticate("bob", "bob123").tenant == "tenant-b"

    csv_path = tmp_path / "iso.csv"
    csv_path.write_text("id,region,amount\n1,east,10\n", encoding="utf-8")

    async with await _client() as client:
        token_a = await _login_tenant(client, "alice", "alice123")
        token_b = await _login_tenant(client, "bob", "bob123")

        # A 建数据源
        resp = await client.post(
            "/api/access/sources",
            json={"name": "tenant-a-source", "source_type": "csv", "file_path": str(csv_path)},
            headers=_auth(token_a),
        )
        assert resp.status_code == 201, resp.text
        sid = resp.json()["id"]

        # B 列表为空, 访问 A 的数据源视为不存在
        resp_b = await client.get("/api/access/sources", headers=_auth(token_b))
        assert resp_b.status_code == 200
        assert resp_b.json() == []

        resp_b2 = await client.get(f"/api/access/sources/{sid}", headers=_auth(token_b))
        assert resp_b2.status_code == 404

        # A 自己可见且可采集
        resp_a = await client.get("/api/access/sources", headers=_auth(token_a))
        assert any(s["name"] == "tenant-a-source" for s in resp_a.json())


@pytest.mark.anyio
async def test_tenant_admin_api(monkeypatch):
    """租户管理: admin 可建/查/停用, 非 admin 拒绝."""
    async with await _client() as client:
        admin_tok = await _login(client)
        ah = _auth(admin_tok)

        # 创建租户
        resp = await client.post("/api/security/tenants", json={"code": "acme", "name": "Acme 集团"}, headers=ah)
        assert resp.status_code == 201, resp.text
        assert resp.json()["code"] == "acme"

        # 列表包含
        resp = await client.get("/api/security/tenants", headers=ah)
        assert any(t["code"] == "acme" for t in resp.json())

        # 停用
        resp = await client.patch("/api/security/tenants/acme", json={"status": "disabled"}, headers=ah)
        assert resp.json()["status"] == "disabled"

        # 非 admin 无权限
        analyst_tok = await _login(client, "analyst", "analyst123")
        resp = await client.post("/api/security/tenants", json={"code": "x", "name": "X"}, headers=_auth(analyst_tok))
        assert resp.status_code in (403, 401)


# ---------- 联邦接入 (M6) ----------


@pytest.mark.anyio
async def test_federation_peer_crud():
    """联邦实例注册 CRUD."""
    async with await _client() as client:
        admin_tok = await _login(client)
        ah = _auth(admin_tok)

        resp = await client.post(
            "/api/access/federation/peers",
            json={"name": "peer-1", "base_url": "http://peer.example:8000", "api_token": "tok-123"},
            headers=ah,
        )
        assert resp.status_code == 201, resp.text
        pid = resp.json()["id"]

        resp = await client.get("/api/access/federation/peers", headers=ah)
        assert any(p["id"] == pid and p["base_url"] == "http://peer.example:8000" for p in resp.json())

        resp = await client.patch(f"/api/access/federation/peers/{pid}", json={"status": "disabled"}, headers=ah)
        assert resp.json()["status"] == "disabled"

        resp = await client.delete(f"/api/access/federation/peers/{pid}", headers=ah)
        assert resp.status_code == 204


@pytest.mark.anyio
async def test_federation_search_empty_without_peers():
    """无启用实例时联邦检索返回空列表."""
    from app.access.federated import federated_search
    from app.core.database import SessionLocal

    async with SessionLocal() as session:
        from app.access.federated import FederatedPeer

        result = await session.execute(select_safe(FederatedPeer))
        for peer in result.scalars():
            await session.delete(peer)
        await session.commit()
        assert await federated_search(session) == []


@pytest.mark.anyio
async def test_federation_search_proxies_peers(monkeypatch):
    """联邦检索并发透传启用实例 (mock 远端结果)."""
    from app.access import federated
    from app.core.database import SessionLocal

    async with SessionLocal() as session:
        from app.access.federated import FederatedPeer, create_peer

        result = await session.execute(select_safe(FederatedPeer))
        for peer in result.scalars():
            await session.delete(peer)
        await session.commit()
        await create_peer(session, "p1", "http://a:8000", None)
        await create_peer(session, "p2", "http://b:8000", None)

        async def fake_request(peer, path, params=None, timeout=15.0):
            return {"ok": True, "peer": peer.name, "data": [{"table_name": f"{peer.name}-tbl"}]}

        monkeypatch.setattr(federated, "_request", fake_request)
        results = await federated.federated_search(session)
        assert len(results) == 2
        assert {r["peer"] for r in results} == {"p1", "p2"}
        assert results[0]["data"][0]["table_name"].endswith("-tbl")


def select_safe(model):
    from sqlalchemy import select
    return select(model)


# ---------- CSV 文件上传接入 (M6) ----------


@pytest.mark.anyio
async def test_csv_upload_creates_source(tmp_path):
    """multipart 上传 CSV -> 数据源创建成功, file_path 指向落盘文件."""
    async with await _client() as client:
        admin_tok = await _login(client)
        ah = _auth(admin_tok)

        csv_content = b"id,region,amount\n1,east,10\n"
        files = {"file": ("orders.csv", csv_content, "text/csv")}
        resp = await client.post(
            "/api/access/sources/upload",
            data={"name": "上传源", "description": "multipart 上传"},
            files=files,
            headers=ah,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["name"] == "上传源"
        assert body["source_type"] == "csv"
        assert body["file_path"] and body["file_path"].endswith("orders.csv")

        # 列表可见
        resp2 = await client.get("/api/access/sources", headers=ah)
        assert any(s["name"] == "上传源" for s in resp2.json())

        # 可采集
        resp3 = await client.post(f"/api/access/sources/{body['id']}/ingest", headers=ah)
        assert resp3.status_code == 200, resp3.text
        assert resp3.json()["tables_found"] == 1


@pytest.mark.anyio
async def test_csv_upload_rejects_non_csv(tmp_path):
    """非 CSV 文件上传被拒绝."""
    async with await _client() as client:
        admin_tok = await _login(client)
        ah = _auth(admin_tok)
        files = {"file": ("note.txt", b"hello", "text/plain")}
        resp = await client.post(
            "/api/access/sources/upload", data={"name": "bad"}, files=files, headers=ah
        )
        assert resp.status_code == 400, resp.text
