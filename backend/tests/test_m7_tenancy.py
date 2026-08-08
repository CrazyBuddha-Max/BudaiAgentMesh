"""M7-2 测试: 多租户扩展到知识 / Agent / 审计层."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings


async def _client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def _login(client: AsyncClient, username: str, password: str) -> str:
    resp = await client.post("/api/security/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _two_tenants(monkeypatch):
    """alice 属 tenant-a, bob 属 tenant-b (default 保留给 admin)."""
    monkeypatch.setattr(
        settings,
        "builtin_users",
        "admin:admin123:admin,alice:alice123:analyst:tenant-a,bob:bob123:analyst:tenant-b",
    )


from app.main import app  # noqa: E402


@pytest.mark.anyio
async def test_knowledge_docs_tenant_isolation(tmp_path):
    """知识文档: A 上传的文档 B 看不到, 越权访问 404, 检索互不可见."""
    async with await _client() as client:
        tok_a = await _login(client, "alice", "alice123")
        tok_b = await _login(client, "bob", "bob123")

        # A 上传知识文档
        resp = await client.post(
            "/api/knowledge/documents",
            files={"file": ("口径说明.md", "# 租户A专属口径\n毛利率=(收入-成本)/收入", "text/markdown")},
            headers=_auth(tok_a),
        )
        assert resp.status_code == 201, resp.text
        doc_id = resp.json()["id"]

        # A 列表可见; B 列表为空
        resp_a = await client.get("/api/knowledge/documents", headers=_auth(tok_a))
        assert any(d["id"] == doc_id for d in resp_a.json())
        resp_b = await client.get("/api/knowledge/documents", headers=_auth(tok_b))
        assert resp_b.json() == []

        # B 直接访问 A 的文档 -> 404
        resp_b2 = await client.get(f"/api/knowledge/documents/{doc_id}", headers=_auth(tok_b))
        assert resp_b2.status_code == 404


@pytest.mark.anyio
async def test_agent_and_tasks_tenant_isolation():
    """Agent 与任务: A 创建的 Agent/任务 B 不可见."""
    async with await _client() as client:
        tok_a = await _login(client, "alice", "alice123")
        tok_b = await _login(client, "bob", "bob123")

        resp = await client.post(
            "/api/agents",
            json={"name": "租户A助手", "capabilities": ["data_access"]},
            headers=_auth(tok_a),
        )
        assert resp.status_code == 201, resp.text
        agent_id = resp.json()["id"]

        # A 可见, B 列表无
        resp_a = await client.get("/api/agents", headers=_auth(tok_a))
        assert any(a["name"] == "租户A助手" for a in resp_a.json())
        resp_b = await client.get("/api/agents", headers=_auth(tok_b))
        assert all(a["name"] != "租户A助手" for a in resp_b.json())

        # B 访问 A 的 Agent -> 404 (删除越权也 404)
        resp_b3 = await client.delete(f"/api/agents/{agent_id}", headers=_auth(tok_b))
        assert resp_b3.status_code == 404

        # A 建任务, B 看不到
        resp_t = await client.post(
            f"/api/agents/{agent_id}/tasks", json={"objective": "租户A的任务"}, headers=_auth(tok_a)
        )
        task_id = resp_t.json()["id"]
        resp_b_tasks = await client.get("/api/agents/tasks", headers=_auth(tok_b))
        assert all(t["id"] != task_id for t in resp_b_tasks.json())
        resp_b_t = await client.get(f"/api/agents/tasks/{task_id}", headers=_auth(tok_b))
        assert resp_b_t.status_code == 404


@pytest.mark.anyio
async def test_audit_logs_tenant_isolation():
    """审计日志: 各租户只见自己的操作记录."""
    async with await _client() as client:
        tok_a = await _login(client, "alice", "alice123")  # 产生 auth.login 审计
        resp = await client.get("/api/security/audit-logs", headers=_auth(tok_a))
        assert resp.status_code == 200
        logs = resp.json()
        # A 的审计里应有 alice 的登录记录
        assert any(x["actor"] == "alice" and x["action"] == "auth.login" for x in logs)
        # 不包含 bob 的记录
        assert all(x["actor"] != "bob" for x in logs)


@pytest.mark.anyio
async def test_template_create_deduplicates_name():
    """重复从模板创建: 重名自动追加序号, 不报'已存在'."""
    async with await _client() as client:
        tok = await _login(client, "alice", "alice123")
        ah = _auth(tok)

        names = []
        for _ in range(2):
            resp = await client.post("/api/agents/from-template", json={"template_key": "data-analyst"}, headers=ah)
            assert resp.status_code == 201, resp.text
            names.append(resp.json()["name"])
        assert names[0] != names[1]
        assert names[1].startswith(names[0])
