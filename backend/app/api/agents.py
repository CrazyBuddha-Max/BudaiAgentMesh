"""协同层 API: Agent 注册 / 工具注册中心 / 任务编排."""

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
from app.agents.schemas import AgentCreate, AgentOut, TaskCreate, TaskOut, ToolInfo
from app.agents.tools import tool_schemas
from app.core.database import get_session
from app.security.auth import AnalystDep, CurrentUserDep

router = APIRouter()

SessionDep = Depends(get_session)


@router.get("", response_model=list[AgentOut])
async def agents(user: CurrentUserDep, session: AsyncSession = SessionDep) -> list[Agent]:
    result = await session.execute(select(Agent).order_by(Agent.created_at.desc()))
    return list(result.scalars().all())


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
        capabilities=template.capabilities,
        tools=[],
        status="active",
    )
    session.add(agent)
    await session.commit()
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
        capabilities=payload.capabilities,
        tools=payload.tools,
        status="active",
    )
    session.add(agent)
    await session.commit()
    await session.refresh(agent)
    return agent


@router.delete("/{agent_id}", status_code=204)
async def remove_agent(agent_id: int, user: AnalystDep, session: AsyncSession = SessionDep) -> None:
    agent = await session.get(Agent, agent_id)
    if agent is not None:
        await session.delete(agent)
        await session.commit()


@router.get("/tools", response_model=list[ToolInfo])
async def tools(user: CurrentUserDep, session: AsyncSession = SessionDep) -> list[ToolInfo]:
    """工具注册中心: 数据能力以标准 Schema 暴露 (MCP 雏形)."""
    return [ToolInfo(**s) for s in tool_schemas(session)]


@router.post("/{agent_id}/tasks", response_model=TaskOut, status_code=201)
async def create_agent_task(
    agent_id: int, payload: TaskCreate, user: AnalystDep, session: AsyncSession = SessionDep
):
    task = await create_task(session, agent_id, payload.objective, payload.title, payload.collaborators)
    return await get_task(session, task.id)


@router.get("/tasks", response_model=list[TaskOut])
async def tasks(user: CurrentUserDep, limit: int = Query(50, le=200), session: AsyncSession = SessionDep):
    return await list_tasks(session, limit)


@router.get("/tasks/{task_id}", response_model=TaskOut)
async def task_detail(task_id: int, user: CurrentUserDep, session: AsyncSession = SessionDep):
    return await get_task(session, task_id)


@router.post("/tasks/{task_id}/run", response_model=TaskOut)
async def run_agent_task(task_id: int, user: AnalystDep, session: AsyncSession = SessionDep):
    """执行任务: 知识检索 -> 目录检索 -> 数据采样 -> 结果组装, 事件全程留痕."""
    await run_task(session, task_id)
    return await get_task(session, task_id)  # 重新拉取, 保证 events 完整
