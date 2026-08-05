"""M3 测试: 动态脱敏 / 审计日志 / 数据血缘 / 反馈闭环 / 多 Agent 协作."""
import os
import shutil
import tempfile

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

CSV_CONTENT = (
    "id,customer_name,phone,amount\n"
    "1,张三,13812345678,10.5\n"
    "2,李四,13987654321,7.0\n"
    "3,王五,13700001111,3.2\n"
)


@pytest.fixture(scope="module")
def csv_file() -> str:
    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, "customer_table.csv")
    with open(path, "w", encoding="utf-8") as f:
        f.write(CSV_CONTENT)
    yield path
    shutil.rmtree(tmpdir, ignore_errors=True)


async def _client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def _login(client: AsyncClient, username: str = "admin", password: str = "admin123") -> str:
    resp = await client.post("/api/security/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _prepare_source(client: AsyncClient, headers: dict, csv_file: str, name: str = "m3-customer-source") -> int:
    resp = await client.post(
        "/api/access/sources",
        headers=headers,
        json={"name": name, "source_type": "csv", "file_path": csv_file},
    )
    assert resp.status_code == 201, resp.text
    source_id = resp.json()["id"]
    resp = await client.post(f"/api/access/sources/{source_id}/ingest", headers=headers)
    assert resp.status_code == 200, resp.text
    resp = await client.get("/api/access/catalog/tables", headers=headers)
    table = next(t for t in resp.json() if t["source_id"] == source_id)
    return table["id"]


# ---------- 动态脱敏 ----------

@pytest.mark.anyio
async def test_dynamic_masking_by_role(csv_file: str):
    async with await _client() as client:
        admin_token = await _login(client, "admin", "admin123")
        await _prepare_source(client, _auth(admin_token), csv_file, "m3-mask-source")

        # 脱敏单元行为: 列识别 + 掩码 + 角色策略
        from app.security.masking import apply_masking, detect_sensitive_columns, mask_value

        detected = detect_sensitive_columns(["customer_name", "phone", "amount"])
        assert detected.get("customer_name") == "name"
        assert detected.get("phone") == "phone"
        assert "amount" not in detected

        assert mask_value("张三", "name") == "张*"
        assert mask_value("13812345678", "phone") == "138****5678"
        assert mask_value("110101199001011234", "id_card").startswith("110")

        rows = [
            {"customer_name": "张三", "phone": "13812345678", "amount": "10.5"},
            {"customer_name": "李四", "phone": "13987654321", "amount": "7.0"},
        ]
        masked = apply_masking(rows, detected, "viewer")
        assert masked[0]["customer_name"] == "张*"
        assert masked[0]["phone"] == "138****5678"
        assert masked[0]["amount"] == "10.5"  # 非敏感列不动

        unmasked = apply_masking(rows, detected, "admin")
        assert unmasked[0]["customer_name"] == "张三"


# ---------- 审计日志 ----------

@pytest.mark.anyio
async def test_audit_logs():
    async with await _client() as client:
        token = await _login(client)
        headers = _auth(token)

        resp = await client.get("/api/security/audit-logs", headers=headers)
        assert resp.status_code == 200
        logs = resp.json()
        # 登录审计应已记录
        assert any("auth.login" in log["action"] for log in logs)
        assert any(log["actor"] == "admin" for log in logs)


# ---------- 血缘 ----------

@pytest.mark.anyio
async def test_lineage_metric_flow(csv_file: str):
    async with await _client() as client:
        token = await _login(client, "analyst", "analyst123")  # analyst: 数据可见但 PII 脱敏
        headers = _auth(token)
        table_id = await _prepare_source(client, headers, csv_file, "m3-lineage-source")

        resp = await client.post(
            "/api/knowledge/metrics",
            headers=headers,
            json={
                "name": "m3_test_amount",
                "display_name": "测试金额",
                "table_id": table_id,
                "measure": "amount",
                "aggregation": "sum",
                "dimensions": ["customer_name"],
                "unit": "元",
            },
        )
        assert resp.status_code == 201, resp.text
        metric_id = resp.json()["id"]

        resp = await client.post(
            f"/api/knowledge/metrics/{metric_id}/query",
            headers=headers,
            json={"group_by": ["customer_name"]},
        )
        assert resp.status_code == 200, resp.text
        # analyst 角色 -> customer_name 应被脱敏
        rows = resp.json()["rows"]
        assert rows and rows[0].get("customer_name", "").endswith("*")

        resp = await client.get("/api/security/lineage", headers=headers)
        assert resp.status_code == 200
        graph = resp.json()
        assert any("metric" in n["type"] for n in graph["nodes"])
        assert any("table" in n["type"] for n in graph["nodes"])


# ---------- 反馈闭环 ----------

@pytest.mark.anyio
async def test_feedback_flow():
    async with await _client() as client:
        token = await _login(client)
        headers = _auth(token)

        # 创建 Agent + 任务
        resp = await client.post("/api/agents", headers=headers, json={"name": "反馈测试助手", "capabilities": []})
        agent_id = resp.json()["id"]
        resp = await client.post(
            f"/api/agents/{agent_id}/tasks", headers=headers, json={"objective": "反馈测试任务"}
        )
        task_id = resp.json()["id"]
        await client.post(f"/api/agents/tasks/{task_id}/run", headers=headers)

        resp = await client.post(
            f"/api/feedback/tasks/{task_id}/feedback",
            headers=headers,
            json={"rating": 5, "comment": "结果准确"},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["rating"] == 5

        resp = await client.post(
            f"/api/feedback/tasks/{task_id}/feedback", headers=headers, json={"rating": 6}
        )
        assert resp.status_code == 422  # Pydantic 范围校验 (1-5)

        resp = await client.get("/api/feedback/stats", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1
        assert resp.json()["avg_rating"] >= 5

        await client.delete(f"/api/agents/{agent_id}", headers=headers)


# ---------- 多 Agent 协作 ----------

@pytest.mark.anyio
async def test_multi_agent_collaboration(csv_file: str):
    async with await _client() as client:
        token = await _login(client)
        headers = _auth(token)
        await _prepare_source(client, headers, csv_file, "m3-multi-source")

        # 注册分工 Agent
        ids = []
        for name, caps in [
            ("M3检索员", ["knowledge_retrieval"]),
            ("M3分析员", ["data_access"]),
            ("M3主控", ["report_draft"]),
        ]:
            resp = await client.post(
                "/api/agents", headers=headers, json={"name": name, "capabilities": caps}
            )
            ids.append(resp.json()["id"])

        main_id, retriever_id, analyst_id = ids
        resp = await client.post(
            f"/api/agents/{main_id}/tasks",
            headers=headers,
            json={"objective": "分析 customer_table 数据", "collaborators": [retriever_id, analyst_id]},
        )
        assert resp.status_code == 201, resp.text
        task_id = resp.json()["id"]

        resp = await client.post(f"/api/agents/tasks/{task_id}/run", headers=headers)
        assert resp.status_code == 200, resp.text
        task = resp.json()
        assert task["status"] == "succeeded", task.get("error")
        assert "customer_table" in (task["result"] or "")
        # 事件应按分工记录不同 agent
        tool_events = [e for e in task["events"] if e["event_type"] == "tool_call"]
        agent_ids_used = {e["agent_id"] for e in tool_events}
        assert retriever_id in agent_ids_used or analyst_id in agent_ids_used

        for aid in ids:
            await client.delete(f"/api/agents/{aid}", headers=headers)
