"""协同层 API: Agent 注册 / 工具注册中心 / 任务编排 / 大模型接入."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import Agent
from app.agents.orchestration import (
    create_task,
    get_task,
    list_tasks,
    run_task,
)
from app.agents.schemas import (
    AgentCreate,
    AgentOut,
    LLMProviderCreate,
    LLMProviderOut,
    TaskCreate,
    TaskOut,
    ToolInfo,
)
from app.agents.tools import tool_schemas
from app.core.database import get_session
from app.core.exceptions import BizError
from app.security.auth import AdminDep, AnalystDep, CurrentUserDep

router = APIRouter()

SessionDep = Depends(get_session)


async def _agent_out(session: AsyncSession, agent: Agent) -> AgentOut:
    """填充模型提供方展示名."""
    out = AgentOut.model_validate(agent)
    if agent.llm_provider_id:
        from app.agents.llm import get_provider

        try:
            provider = await get_provider(session, agent.llm_provider_id)
            out.llm_provider_name = provider.name
        except Exception:
            out.llm_provider_name = None
    return out


@router.get("", response_model=list[AgentOut])
async def agents(user: CurrentUserDep, session: AsyncSession = SessionDep) -> list[AgentOut]:
    result = await session.execute(
        select(Agent).where(Agent.tenant_id == user.tenant).order_by(Agent.created_at.desc())
    )
    rows = list(result.scalars().all())
    return [await _agent_out(session, a) for a in rows]


# ---------- Agent 模板市场 (M4) ----------

@router.get("/templates")
async def agent_templates(user: CurrentUserDep) -> list[dict]:
    """Agent 模板市场: 预置角色模板, 一键创建专业化 Agent (M4)."""
    from app.agents.templates import templates_out

    return templates_out()


@router.post("/from-template", response_model=AgentOut, status_code=201)
async def create_from_template(
    payload: dict, user: AnalystDep, session: AsyncSession = SessionDep
) -> Agent:
    """从模板创建 Agent: {template_key, name?}."""
    from app.agents.templates import get_template
    from app.core.exceptions import BizError

    try:
        template = get_template(payload["template_key"])
    except KeyError as exc:
        raise BizError(f"未知模板: {exc}") from exc
    agent = Agent(
        name=payload.get("name") or template.name,
        description=template.description,
        tenant_id=user.tenant,
        llm_provider_id=payload.get("llm_provider_id"),
        capabilities=template.capabilities,
        tools=[],
        status="active",
    )
    session.add(agent)
    try:
        await session.commit()
    except Exception as exc:
        await session.rollback()
        raise BizError(f"Agent 名称已存在: {agent.name}", code="AGENT_NAME_TAKEN") from exc
    await session.refresh(agent)
    return agent


@router.get("/bus/stats")
async def bus_stats(user: CurrentUserDep) -> dict:
    """事件总线运行状态 (M4): 发布量 / 队列积压 / 类型."""
    from app.agents.bus import bus

    return bus.stats() if hasattr(bus, "stats") else {"type": "kafka"}


@router.post("", response_model=AgentOut, status_code=201)
async def create_agent(
    payload: AgentCreate, user: AnalystDep, session: AsyncSession = SessionDep
) -> Agent:
    agent = Agent(
        name=payload.name,
        description=payload.description,
        tenant_id=user.tenant,
        llm_provider_id=payload.llm_provider_id,
        capabilities=payload.capabilities,
        tools=payload.tools,
        status="active",
    )
    session.add(agent)
    try:
        await session.commit()
    except Exception as exc:  # 唯一约束冲突 -> 友好提示
        await session.rollback()

        raise BizError(f"Agent 名称已存在: {payload.name}", code="AGENT_NAME_TAKEN") from exc
    await session.refresh(agent)
    return agent


@router.delete("/{agent_id}", status_code=204)
async def remove_agent(agent_id: int, user: AnalystDep, session: AsyncSession = SessionDep) -> None:
    from app.agents.orchestration import get_agent

    agent = await get_agent(session, agent_id, tenant=user.tenant)
    await session.delete(agent)
    await session.commit()


@router.patch("/{agent_id}", response_model=AgentOut)
async def patch_agent(
    agent_id: int, payload: dict, user: AnalystDep, session: AsyncSession = SessionDep
) -> AgentOut:
    """编辑 Agent (M7): 名称/描述/绑定的模型提供方/状态/能力."""
    from app.agents.orchestration import get_agent

    agent = await get_agent(session, agent_id, tenant=user.tenant)
    if "llm_provider_id" in payload:
        provider_id = payload.get("llm_provider_id")
        if provider_id is not None:
            from app.agents.llm import get_provider

            await get_provider(session, int(provider_id))  # 校验存在
        agent.llm_provider_id = int(provider_id) if provider_id else None
    for field in ("name", "description", "status", "capabilities", "tools"):
        if field in payload and payload[field] is not None:
            setattr(agent, field, payload[field])
    await session.commit()
    await session.refresh(agent)
    return await _agent_out(session, agent)


@router.get("/tools", response_model=list[ToolInfo])
async def tools(user: CurrentUserDep, session: AsyncSession = SessionDep) -> list[ToolInfo]:
    """工具注册中心: 数据能力以标准 Schema 暴露 (MCP 雏形)."""
    return [ToolInfo(**s) for s in tool_schemas(session)]


@router.post("/{agent_id}/tasks", response_model=TaskOut, status_code=201)
async def create_agent_task(
    agent_id: int, payload: TaskCreate, user: AnalystDep, session: AsyncSession = SessionDep
):
    task = await create_task(session, agent_id, payload.objective, payload.title, payload.collaborators, tenant=user.tenant)
    return await get_task(session, task.id, tenant=user.tenant)


@router.get("/tasks", response_model=list[TaskOut])
async def tasks(user: CurrentUserDep, limit: int = Query(50, le=200), session: AsyncSession = SessionDep):
    return await list_tasks(session, limit, tenant=user.tenant)


@router.get("/tasks/{task_id}", response_model=TaskOut)
async def task_detail(task_id: int, user: CurrentUserDep, session: AsyncSession = SessionDep):
    return await get_task(session, task_id, tenant=user.tenant)


@router.post("/tasks/{task_id}/run", response_model=TaskOut)
async def run_agent_task(task_id: int, user: AnalystDep, session: AsyncSession = SessionDep):
    """执行任务: 知识检索 -> 目录检索 -> 数据采样 -> LLM 规划/汇总, 事件全程留痕."""
    await run_task(session, task_id, tenant=user.tenant)
    return await get_task(session, task_id, tenant=user.tenant)  # 重新拉取, 保证 events 完整


# ---------- 大模型接入 (M7) ----------

@router.get("/capabilities")
async def capabilities(user: CurrentUserDep) -> list[dict]:
    """能力注册表: 新建 Agent 时动态选择能力 (新增能力无需改代码)."""
    from app.agents.capabilities import capabilities_out

    return capabilities_out()


@router.get("/llm/providers", response_model=list[LLMProviderOut])
async def llm_providers(user: CurrentUserDep, session: AsyncSession = SessionDep):
    """模型提供方列表 (密钥不回显)."""
    from app.agents.llm import list_providers

    return await list_providers(session)


@router.post("/llm/providers", response_model=LLMProviderOut, status_code=201)
async def create_llm_provider(
    payload: LLMProviderCreate, user: AdminDep, session: AsyncSession = SessionDep
):
    """新增模型提供方 (admin): OpenAI/DeepSeek/通义/Ollama 等 OpenAI 兼容协议."""
    from app.agents.llm import create_provider

    return await create_provider(
        session,
        name=payload.name,
        provider_type=payload.provider_type,
        api_base=payload.api_base,
        api_key=payload.api_key,
        model=payload.model,
        embedding_model=payload.embedding_model,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        is_default=payload.is_default,
    )


@router.patch("/llm/providers/{provider_id}", response_model=LLMProviderOut)
async def patch_llm_provider(
    provider_id: int, payload: dict, user: AdminDep, session: AsyncSession = SessionDep
):
    """更新模型提供方 (admin): api_key 传空则不修改."""
    from app.agents.llm import update_provider

    return await update_provider(session, provider_id, payload)


@router.delete("/llm/providers/{provider_id}", status_code=204)
async def remove_llm_provider(
    provider_id: int, user: AdminDep, session: AsyncSession = SessionDep
) -> None:
    from app.agents.llm import delete_provider

    await delete_provider(session, provider_id)


@router.post("/llm/providers/{provider_id}/test")
async def test_llm_provider(
    provider_id: int, user: AdminDep, session: AsyncSession = SessionDep
) -> dict:
    """测试连接: 发送最小对话请求验证可用性."""
    from app.agents.llm import get_provider, test_connection

    provider = await get_provider(session, provider_id)
    message = await test_connection(provider)
    return {"provider_id": provider_id, "name": provider.name, "message": message}


@router.post("/llm/providers/{provider_id}/default", response_model=LLMProviderOut)
async def set_llm_default(
    provider_id: int, user: AdminDep, session: AsyncSession = SessionDep
):
    """设为默认: 未绑定模型的 Agent / 知识向量化默认使用."""
    from app.agents.llm import set_default_provider

    return await set_default_provider(session, provider_id)
