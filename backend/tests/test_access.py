"""接入层与认证核心测试."""
import os
import shutil
import tempfile

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

CSV_CONTENT = """id,name,amount,note
1,alpha,10.5,ok
2,beta,,warn
3,gamma,7.0,ok
4,delta,3.2,ok
"""


@pytest.fixture(scope="module")
def csv_file() -> str:
    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, "demo_table.csv")
    with open(path, "w", encoding="utf-8") as f:
        f.write(CSV_CONTENT)
    yield path
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


async def _client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def _login(client: AsyncClient, username: str = "admin", password: str = "admin123") -> str:
    resp = await client.post("/api/security/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_health():
    async with await _client() as client:
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


@pytest.mark.anyio
async def test_login_and_me():
    async with await _client() as client:
        token = await _login(client)
        resp = await client.get("/api/security/me", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["username"] == "admin"
        assert resp.json()["role"] == "admin"


@pytest.mark.anyio
async def test_login_rejected():
    async with await _client() as client:
        resp = await client.post("/api/security/login", json={"username": "admin", "password": "wrong"})
        assert resp.status_code == 401


@pytest.mark.anyio
async def test_requires_auth():
    async with await _client() as client:
        resp = await client.get("/api/access/sources")
        assert resp.status_code == 401


@pytest.mark.anyio
async def test_viewer_cannot_create_source():
    async with await _client() as client:
        token = await _login(client, "viewer", "viewer123")
        resp = await client.post(
            "/api/access/sources",
            json={"name": "should-fail", "source_type": "csv"},
            headers=_auth(token),
        )
        assert resp.status_code == 403


@pytest.mark.anyio
async def test_csv_source_full_flow(csv_file: str):
    async with await _client() as client:
        token = await _login(client)
        headers = _auth(token)

        resp = await client.post(
            "/api/access/sources",
            json={
                "name": "demo-csv",
                "source_type": "csv",
                "description": "测试数据源",
                "file_path": csv_file,
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        source = resp.json()
        source_id = source["id"]
        # 口令等敏感字段不返回
        assert "password" not in resp.text
        assert source["status"] == "pending"

        resp = await client.post(f"/api/access/sources/{source_id}/test", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

        resp = await client.post(f"/api/access/sources/{source_id}/ingest", headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "success"
        assert resp.json()["tables_found"] == 1

        resp = await client.get("/api/access/catalog/stats", headers=headers)
        assert resp.json()["sources"] >= 1
        assert resp.json()["tables"] >= 1

        resp = await client.get("/api/access/catalog/tables", headers=headers)
        tables = resp.json()
        assert len(tables) >= 1
        table = tables[0]
        assert table["row_count"] == 4
        # 质量初检: note 列存在空值
        amount_col = next(c for c in table["columns"] if c["column_name"] == "amount")
        assert amount_col["null_rate"] > 0

        resp = await client.get(
            "/api/access/catalog/columns", params={"keyword": "amount"}, headers=headers
        )
        assert resp.status_code == 200
        assert any(c["column_name"] == "amount" for c in resp.json())

        resp = await client.get("/api/access/connectors", headers=headers)
        types = {c["type"] for c in resp.json()}
        assert {"csv", "postgres", "mysql"} <= types

        # 观测指标
        resp = await client.get("/api/feedback/metrics", headers=headers)
        assert resp.status_code == 200
        assert "requests" in resp.json()

        resp = await client.delete(f"/api/access/sources/{source_id}", headers=headers)
        assert resp.status_code == 204
