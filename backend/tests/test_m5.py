"""M5 测试: 列级权限 / 数据生命周期 / MCP Server."""
import os
import shutil
import tempfile

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

CSV_CONTENT = "id,customer_name,phone,amount\n1,张三,13812345678,100\n2,李四,13987654321,200\n3,王五,13711112222,300\n"


@pytest.fixture(scope="module")
def csv_file() -> str:
    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, "m5_cust.csv")
    with open(path, "w", encoding="utf-8") as f:
        f.write(CSV_CONTENT)
    yield path
    shutil.rmtree(tmpdir, ignore_errors=True)


async def _client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def _login(client: AsyncClient, username: str = "admin", password: str = "admin123") -> str:
    resp = await client.post("/api/security/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _prepare(client: AsyncClient, headers: dict, csv_file: str, name: str = "m5-cust-source") -> int:
    resp = await client.post(
        "/api/access/sources",
        headers=headers,
        json={"name": name, "source_type": "csv", "file_path": csv_file},
    )
    assert resp.status_code == 201, resp.text
    sid = resp.json()["id"]
    await client.post(f"/api/access/sources/{sid}/ingest", headers=headers)
    resp = await client.get("/api/access/catalog/tables", headers=headers)
    return next(t["id"] for t in resp.json() if t["source_id"] == sid)


# ---------- 列级权限 ----------

@pytest.mark.anyio
async def test_column_acl(csv_file: str):
    async with await _client() as client:
        admin_tok = await _login(client)
        ah = _auth(admin_tok)
        table_id = await _prepare(client, ah, csv_file)

        # admin 配置: analyst 禁止访问 phone 列
        resp = await client.post(
            "/api/security/column-policies",
            headers=ah,
            json={"role": "analyst", "table_id": table_id, "column_name": "phone"},
        )
        assert resp.status_code == 201, resp.text
        policy_id = resp.json()["id"]

        # 数据工具经 analyst 调用 -> phone 列被剔除
        from app.access.catalog import query_table_rows
        from app.core.database import SessionLocal

        async with SessionLocal() as s:
            result = await query_table_rows(s, table_id, limit=5, actor="t", role="analyst")
            assert result["rows"] and "phone" not in result["rows"][0]
            assert "customer_name" in result["rows"][0]  # 其它列不受影响

        # admin 角色不受影响
        async with SessionLocal() as s:
            result = await query_table_rows(s, table_id, limit=5, actor="t", role="admin")
            assert "phone" in result["rows"][0]

        # 指标按被禁列下钻 -> 拒绝
        resp = await client.post(
            "/api/knowledge/metrics",
            headers=ah,
            json={
                "name": "m5_amount", "display_name": "M5金额", "table_id": table_id,
                "measure": "amount", "aggregation": "sum", "dimensions": ["customer_name", "phone"],
            },
        )
        metric_id = resp.json()["id"]
        an_tok = await _login(client, "analyst", "analyst123")
        resp = await client.post(
            f"/api/knowledge/metrics/{metric_id}/query",
            headers=_auth(an_tok),
            json={"group_by": ["phone"]},
        )
        assert resp.status_code == 400  # 越权维度被拦截
        assert "phone" in resp.text

        # 清理
        await client.delete(f"/api/security/column-policies/{policy_id}", headers=ah)
        await client.delete(f"/api/knowledge/metrics/{metric_id}", headers=ah)


# ---------- 数据生命周期 ----------

@pytest.mark.anyio
async def test_lifecycle(csv_file: str):
    async with await _client() as client:
        tok = await _login(client)
        headers = _auth(tok)
        await _prepare(client, headers, csv_file, "m5-lifecycle-source")
        # 按名称定位数据源 id
        resp = await client.get("/api/access/sources", headers=headers)
        source_id = next(s["id"] for s in resp.json() if s["name"] == "m5-lifecycle-source")

        # 默认无策略
        resp = await client.get("/api/security/lifecycle", headers=headers)
        item = next(i for i in resp.json()["items"] if i["source_id"] == source_id)
        assert item["status"] == "no-policy"

        # 设置保留期 30 天 -> 活跃
        resp = await client.patch(
            f"/api/access/sources/{source_id}", headers=headers, json={"retention_days": 30}
        )
        assert resp.status_code == 200, resp.text
        resp = await client.get("/api/security/lifecycle", headers=headers)
        item = next(i for i in resp.json()["items"] if i["source_id"] == source_id)
        assert item["status"] == "active"
        assert item["expires_at"] is not None

        # 统计接口
        assert resp.json()["summary"]["total"] >= 1

        # 还原
        await client.patch(f"/api/access/sources/{source_id}", headers=headers, json={"retention_days": None})


# ---------- MCP Server ----------

@pytest.mark.anyio
async def test_mcp_tools():
    from app.agents.mcp_server import (
        catalog_search_tables,
        knowledge_retrieve,
        mcp,
    )

    # 工具函数可直接调用 (各自开独立会话)
    hits = await knowledge_retrieve("毛利率口径", 2)
    assert hits.startswith("[")  # 知识库可能为空, 契约保证返回 JSON 数组

    tables = await catalog_search_tables("不存在表xyz")
    assert tables.startswith("[")

    # /mcp 已挂载
    paths = [getattr(r, "path", "") for r in app.routes]
    assert any("/mcp" in p for p in paths)

    # 工具清单: fastmcp 3.x 用 list_tools 方法
    listed = mcp.list_tools()
    assert listed, "MCP 工具清单为空"
