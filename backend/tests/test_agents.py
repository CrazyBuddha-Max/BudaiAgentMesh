"""协同层测试: Agent 注册 / 工具注册中心 / 任务编排 (自建数据源)."""
import os
import shutil
import tempfile

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

CSV_CONTENT = "id,name,amount\n1,alpha,10.5\n2,beta,7.0\n3,gamma,3.2\n"


@pytest.fixture(scope="module")
def csv_file() -> str:
    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, "demo_table.csv")
    with open(path, "w", encoding="utf-8") as f:
        f.write(CSV_CONTENT)
    yield path
    shutil.rmtree(tmpdir, ignore_errors=True)


async def _client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def _login(client: AsyncClient) -> str:
    resp = await client.post("/api/security/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_agent_full_flow(csv_file: str):
    async with await _client() as client:
        token = await _login(client)
        headers = _auth(token)

        # 准备数据: CSV 源 + 采集
        resp = await client.post(
            "/api/access/sources",
            headers=headers,
            json={"name": "agent-demo-source", "source_type": "csv", "file_path": csv_file},
        )
        assert resp.status_code == 201, resp.text
        source_id = resp.json()["id"]
        resp = await client.post(f"/api/access/sources/{source_id}/ingest", headers=headers)
        assert resp.status_code == 200, resp.text

        # Agent 注册
        resp = await client.post(
            "/api/agents",
            headers=headers,
            json={
                "name": "测试助手",
                "description": "协同层测试",
                "capabilities": ["knowledge_retrieval", "data_access"],
                "tools": [],
            },
        )
        assert resp.status_code == 201, resp.text
        agent_id = resp.json()["id"]

        # 工具注册中心
        resp = await client.get("/api/agents/tools", headers=headers)
        names = {t["name"] for t in resp.json()}
        assert {"knowledge.retrieve", "catalog.search_tables", "data.query_table"} <= names

        # 创建并执行任务
        resp = await client.post(
            f"/api/agents/{agent_id}/tasks",
            headers=headers,
            json={"objective": "查找 demo_table 数据并采样"},
        )
        assert resp.status_code == 201, resp.text
        task_id = resp.json()["id"]

        resp = await client.post(f"/api/agents/tasks/{task_id}/run", headers=headers)
        assert resp.status_code == 200, resp.text
        task = resp.json()
        assert task["status"] == "succeeded", task.get("error")
        assert "demo_table" in (task["result"] or "")
        event_types = [e["event_type"] for e in task["events"]]
        assert "task_started" in event_types
        assert "tool_call" in event_types
        assert "completion" in event_types

        resp = await client.get("/api/agents/tasks", headers=headers)
        assert any(t["id"] == task_id for t in resp.json())

        # 清理
        resp = await client.delete(f"/api/agents/{agent_id}", headers=headers)
        assert resp.status_code == 204
        resp = await client.delete(f"/api/access/sources/{source_id}", headers=headers)
        assert resp.status_code == 204
