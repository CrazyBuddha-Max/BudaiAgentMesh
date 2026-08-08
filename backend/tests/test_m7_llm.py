"""M7 测试: 大模型接入 (LLM Provider CRUD / 加密 / 统一调用 / 编排降级)."""
import pytest
from httpx import ASGITransport, AsyncClient

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


def _payload(**overrides):
    data = {
        "name": "测试提供方",
        "provider_type": "openai",
        "api_base": "http://mock-llm/v1",
        "api_key": "sk-test-123",
        "model": "mock-chat",
        "embedding_model": "mock-embed",
        "temperature": 0.1,
        "max_tokens": 512,
        "is_default": False,
    }
    data.update(overrides)
    return data


@pytest.mark.anyio
async def test_llm_provider_crud_roundtrip():
    """创建 -> 密钥加密不回显 -> 更新 -> 设默认 -> 删除."""
    async with await _client() as client:
        token = await _login(client)
        ah = _auth(token)

        # 创建
        resp = await client.post("/api/agents/llm/providers", json=_payload(), headers=ah)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        pid = body["id"]
        assert body["name"] == "测试提供方"
        assert "api_key" not in body and "api_key_enc" not in body  # 密钥绝不回显

        # 列表
        resp = await client.get("/api/agents/llm/providers", headers=ah)
        assert any(p["id"] == pid for p in resp.json())

        # 更新
        resp = await client.patch(f"/api/agents/llm/providers/{pid}", json={"temperature": 0.5}, headers=ah)
        assert resp.status_code == 200
        assert resp.json()["temperature"] == 0.5

        # 设默认
        resp = await client.post(f"/api/agents/llm/providers/{pid}/default", headers=ah)
        assert resp.json()["is_default"] is True

        # 删除
        resp = await client.delete(f"/api/agents/llm/providers/{pid}", headers=ah)
        assert resp.status_code == 204

        # 非 admin 拒绝
        analyst = await _login(client, "analyst", "analyst123")
        resp = await client.post("/api/agents/llm/providers", json=_payload(name="x"), headers=_auth(analyst))
        assert resp.status_code in (403, 401)


@pytest.mark.anyio
async def test_llm_provider_validation():
    """非法类型/空字段被拒绝."""
    async with await _client() as client:
        token = await _login(client)
        ah = _auth(token)
        resp = await client.post(
            "/api/agents/llm/providers", json=_payload(provider_type="unknown"), headers=ah
        )
        assert resp.status_code == 400
        resp = await client.post("/api/agents/llm/providers", json=_payload(model=""), headers=ah)
        assert resp.status_code == 400


@pytest.mark.anyio
async def test_chat_completion_real_http(monkeypatch):
    """统一调用: chat_completion 走真实 HTTP (MockTransport)."""
    import httpx

    from app.agents import llm
    from app.core.database import SessionLocal

    async with SessionLocal() as session:
        from app.agents.llm import create_provider

        provider = await create_provider(
            session, "MockLLM", "custom", "http://mock-llm/v1",
            api_key="sk-1", model="chat-1", embedding_model="embed-1",
        )

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/chat/completions"):
                assert request.headers["Authorization"] == "Bearer sk-1"  # 密钥已解密注入
                return httpx.Response(
                    200,
                    json={"choices": [{"message": {"content": "这是模型回复"}}]},
                )
            if request.url.path.endswith("/embeddings"):
                return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2, 0.3]}]})
            return httpx.Response(404)

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://mock-llm"
        ) as _mock_ctx:
            # 注入 mock client: 直接替换 _headers 验证 + 用 to_thread 简化——改为直接测 HTTP 路径
            # chat_completion 内部自建 client, 这里 monkeypatch httpx.AsyncClient
            real_ac = httpx.AsyncClient

            class _MockAC(real_ac):  # type: ignore[misc]
                pass

            # 更简单: 用 monkeypatch 替换 llm.httpx.AsyncClient 为预置 transport 的类
            from functools import partial

            monkeypatch.setattr(
                llm.httpx,
                "AsyncClient",
                partial(real_ac, transport=httpx.MockTransport(handler), base_url="http://mock-llm"),
            )
            reply = await llm.chat_completion(provider, [{"role": "user", "content": "hi"}])
            assert reply == "这是模型回复"

            vecs = await llm.embed_texts(provider, ["hello"])
            assert vecs == [[0.1, 0.2, 0.3]]


@pytest.mark.anyio
async def test_orchestration_llm_plan_and_summary(monkeypatch):
    """编排真实 LLM: 规划/汇总事件出现, 结论带 LLM 标记; 未配置提供方时模板降级."""

    async with await _client() as client:
        token = await _login(client)
        ah = _auth(token)

        # 建一个 Agent
        resp = await client.post(
            "/api/agents",
            json={"name": "LLM 测试 Agent", "capabilities": ["data_access", "knowledge_retrieval"]},
            headers=ah,
        )
        assert resp.status_code == 201, resp.text
        agent_id = resp.json()["id"]

        # 场景 A: 无任何提供方 -> 任务跑通且为模板结果 (降级)
        resp = await client.post(
            f"/api/agents/{agent_id}/tasks", json={"objective": "分析测试"}, headers=ah
        )
        task_id = resp.json()["id"]
        resp = await client.post(f"/api/agents/tasks/{task_id}/run", headers=ah)
        assert resp.status_code == 200, resp.text
        result = resp.json()
        assert result["status"] == "succeeded"

        # 场景 B: 配置默认提供方 + mock LLM -> 规划/汇总走真实调用
        from app.agents import llm
        from app.core.database import SessionLocal

        async def fake_chat(provider, messages, temperature=None, max_tokens=None):
            user_msg = next(m["content"] for m in messages if m["role"] == "user")
            if "知识检索" in messages[0]["content"] or "工具" in messages[0]["content"]:
                return '["knowledge.retrieve", "catalog.search_tables"]'
            return f"结论: 已完成分析 ({user_msg[:20]}...)"

        monkeypatch.setattr(llm, "chat_completion", fake_chat)

        async with SessionLocal() as session:
            from app.agents.llm import create_provider

            await create_provider(
                session, "FakeLLM", "custom", "http://mock/v1", api_key="k", model="m", is_default=True
            )

        resp2 = await client.post(
            f"/api/agents/{agent_id}/tasks", json={"objective": "分析订单毛利率"}, headers=ah
        )
        task_id2 = resp2.json()["id"]
        resp2 = await client.post(f"/api/agents/tasks/{task_id2}/run", headers=ah)
        assert resp2.status_code == 200, resp2.text
        body2 = resp2.json()
        assert body2["status"] == "succeeded"
        assert "LLM 汇总" in (body2["result"] or "")
        event_types = {e["event_type"] for e in body2["events"]}
        assert "llm.plan" in event_types
        assert "llm.summary" in event_types

        # 清理
        await client.delete(f"/api/agents/{agent_id}", headers=ah)


# ---------- Agent 编辑模型绑定 (M7) ----------


@pytest.mark.anyio
async def test_agent_edit_llm_provider_binding():
    """创建 Agent -> 编辑绑定模型 -> 更新名称/描述 -> 解除绑定."""
    async with await _client() as client:
        token = await _login(client)
        ah = _auth(token)

        # 建提供方
        resp = await client.post("/api/agents/llm/providers", json=_payload(name="绑定用模型"), headers=ah)
        pid = resp.json()["id"]

        # 建 Agent
        resp = await client.post(
            "/api/agents", json={"name": "可编辑 Agent", "capabilities": ["data_access"]}, headers=ah
        )
        agent_id = resp.json()["id"]

        # 编辑: 绑定模型 + 改名
        resp = await client.patch(
            f"/api/agents/{agent_id}",
            json={"llm_provider_id": pid, "name": "可编辑 Agent v2", "description": "已编辑"},
            headers=ah,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["llm_provider_id"] == pid
        assert body["name"] == "可编辑 Agent v2"

        # 解除绑定
        resp = await client.patch(f"/api/agents/{agent_id}", json={"llm_provider_id": None}, headers=ah)
        assert resp.json()["llm_provider_id"] is None

        # 绑定不存在的提供方 -> 404
        resp = await client.patch(f"/api/agents/{agent_id}", json={"llm_provider_id": 99999}, headers=ah)
        assert resp.status_code == 404

        # 清理
        await client.delete(f"/api/agents/{agent_id}", headers=ah)
        await client.delete(f"/api/agents/llm/providers/{pid}", headers=ah)
