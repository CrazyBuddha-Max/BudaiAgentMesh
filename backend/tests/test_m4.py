"""M4 测试: 事件总线 / Agent 模板市场 / 真并行 DAG."""
import asyncio
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
    path = os.path.join(tmpdir, "m4_table.csv")
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


# ---------- 事件总线 ----------

@pytest.mark.anyio
async def test_in_process_bus():
    from app.agents.bus import InProcessBus

    bus = InProcessBus()
    received: list[dict] = []

    async def handler(event: dict) -> None:
        received.append(event)

    bus.subscribe(handler)
    await bus.start()
    try:
        await bus.publish("agent.task", {"task_id": 1, "event_type": "tool_call"})
        await bus.publish("agent.task", {"task_id": 1, "event_type": "tool_result"})
        # 等待 Worker 消费
        for _ in range(50):
            if len(received) >= 2:
                break
            await asyncio.sleep(0.01)
        assert len(received) == 2
        assert received[0]["topic"] == "agent.task"
        assert received[0]["event_type"] == "tool_call"
        stats = bus.stats()
        assert stats["published"] >= 2
    finally:
        await bus.stop()


# ---------- Agent 模板市场 ----------

@pytest.mark.anyio
async def test_agent_templates():
    async with await _client() as client:
        token = await _login(client)
        headers = _auth(token)

        resp = await client.get("/api/agents/templates", headers=headers)
        assert resp.status_code == 200
        templates = resp.json()
        assert len(templates) >= 4
        keys = {t["key"] for t in templates}
        assert "analyst-assistant" in keys and "knowledge-retriever" in keys

        resp = await client.post(
            "/api/agents/from-template",
            headers=headers,
            json={"template_key": "knowledge-retriever", "name": "模板创建检索员"},
        )
        assert resp.status_code == 201, resp.text
        agent = resp.json()
        assert agent["name"] == "模板创建检索员"
        assert "knowledge_retrieval" in agent["capabilities"]

        # 未知模板 -> 400
        resp = await client.post(
            "/api/agents/from-template", headers=headers, json={"template_key": "nope"}
        )
        assert resp.status_code == 400

        resp = await client.delete(f"/api/agents/{agent['id']}", headers=headers)
        assert resp.status_code == 204


# ---------- 真并行 DAG ----------

@pytest.mark.anyio
async def test_parallel_dag(csv_file: str):
    async with await _client() as client:
        token = await _login(client)
        headers = _auth(token)

        # 准备数据源
        resp = await client.post(
            "/api/access/sources",
            headers=headers,
            json={"name": "m4-parallel-source", "source_type": "csv", "file_path": csv_file},
        )
        source_id = resp.json()["id"]
        await client.post(f"/api/access/sources/{source_id}/ingest", headers=headers)

        # 分工 Agent
        ids = []
        for name, caps in [
            ("M4检索员", ["knowledge_retrieval"]),
            ("M4分析员", ["data_access"]),
            ("M4主控", ["report_draft"]),
        ]:
            resp = await client.post("/api/agents", headers=headers, json={"name": name, "capabilities": caps})
            ids.append(resp.json()["id"])
        retriever_id, analyst_id, main_id = ids

        resp = await client.post(
            f"/api/agents/{main_id}/tasks",
            headers=headers,
            json={"objective": "分析 m4_table 数据", "collaborators": [retriever_id, analyst_id]},
        )
        task_id = resp.json()["id"]
        resp = await client.post(f"/api/agents/tasks/{task_id}/run", headers=headers)
        task = resp.json()
        assert task["status"] == "succeeded", task.get("error")
        assert "并行" in (task["result"] or "")
        # 两个分支的事件都按分工 Agent 记录
        tool_calls = {e["agent_id"]: e for e in task["events"] if e["event_type"] == "tool_call"}
        assert retriever_id in tool_calls
        assert analyst_id in tool_calls

        # 事件总线统计
        resp = await client.get("/api/agents/bus/stats", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["published"] >= 1

        for aid in ids:
            await client.delete(f"/api/agents/{aid}", headers=headers)
        await client.delete(f"/api/access/sources/{source_id}", headers=headers)
