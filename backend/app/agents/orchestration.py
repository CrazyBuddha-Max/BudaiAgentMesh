"""编排引擎 (M4): 多 Agent 协作 DAG + 真并行执行 + 事件总线.

流程: 主控规划 -> [知识检索 || 目录检索] (真并行, 各分支独立会话)
      -> 数据采样 -> 主控汇总.
事件: 直落库 (UI 权威数据) + 发布到消息总线 (订阅者: 审计/观测/Kafka 适配).
"""
import asyncio
import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.bus import bus
from app.agents.models import Agent, AgentEvent, AgentTask
from app.agents.tools import execute_tool
from app.core.database import SessionLocal
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger

logger = get_logger(__name__)


async def get_agent(session: AsyncSession, agent_id: int) -> Agent:
    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise NotFoundError(f"Agent 不存在: {agent_id}")
    return agent


async def create_task(
    session: AsyncSession,
    agent_id: int,
    objective: str,
    title: str | None = None,
    collaborators: list[int] | None = None,
) -> AgentTask:
    """创建任务: 主控 Agent + 可选协作 Agent 列表."""
    await get_agent(session, agent_id)
    for cid in collaborators or []:
        await get_agent(session, cid)
    task = AgentTask(
        agent_id=agent_id,
        objective=objective,
        title=title or objective[:40],
        status="pending",
        collaborators=collaborators or [],
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


def _pick_executor(main_agent: Agent, collaborators: list[Agent], capability: str) -> Agent:
    """按能力声明挑选执行者: 优先协作 Agent (分工), 主控兜底."""
    for agent in collaborators:
        if capability in (agent.capabilities or []):
            return agent
    if capability in (main_agent.capabilities or []):
        return main_agent
    return main_agent


async def run_task(session: AsyncSession, task_id: int) -> AgentTask:
    """执行任务: 并行分支独立会话, 事件直落库 + 发布总线."""
    from app.security.audit import record_audit

    task = await get_task(session, task_id)
    main_agent = await get_agent(session, task.agent_id)
    collaborators = [await get_agent(session, cid) for cid in (task.collaborators or [])]
    team = [main_agent, *collaborators]
    team_names = " + ".join(a.name for a in team)

    async def emit(
        branch_session: AsyncSession, event_type: str, agent_id: int, payload: dict | None = None
    ) -> None:
        branch_session.add(AgentEvent(task_id=task.id, agent_id=agent_id, event_type=event_type, payload=payload))
        await branch_session.commit()
        await bus.publish(
            "agent.task",
            {"task_id": task.id, "agent_id": agent_id, "event_type": event_type, "payload": payload},
        )

    task.status = "running"
    task.error = None
    await session.commit()
    await emit(session, "task_started", main_agent.id, {"objective": task.objective, "team": team_names})

    try:
        await emit(
            session, "plan", main_agent.id,
            {"steps": ["knowledge.retrieve", "catalog.search_tables", "data.query_table"]},
        )

        # 分工: 优先协作 Agent 承担专业步骤, 主控规划与汇总
        retriever = _pick_executor(main_agent, collaborators, "knowledge_retrieval")
        analyst = _pick_executor(main_agent, collaborators, "data_access")
        reporter = main_agent

        # ---- 并行分支 (M4): 独立会话, asyncio.gather 真并行 ----
        async def branch_retrieve() -> list:
            async with SessionLocal() as bs:
                await emit(bs, "tool_call", retriever.id, {"tool": "knowledge.retrieve", "args": {"query": task.objective, "top_k": 3}})
                resp = await execute_tool(bs, "knowledge.retrieve", {"query": task.objective, "top_k": 3})
                if not resp.get("ok"):
                    raise RuntimeError(f"知识检索失败: {resp.get('error')}")
                hits = resp["result"]
                await emit(bs, "tool_result", retriever.id, {"tool": "knowledge.retrieve", "summary": _summarize(hits)})
                return hits

        async def branch_search() -> list:
            async with SessionLocal() as bs:
                await emit(bs, "tool_call", analyst.id, {"tool": "catalog.search_tables", "args": {"keyword": task.objective[:32]}})
                resp = await execute_tool(bs, "catalog.search_tables", {"keyword": task.objective[:32]})
                if not resp.get("ok"):
                    raise RuntimeError(f"目录检索失败: {resp.get('error')}")
                hits = resp["result"]
                await emit(bs, "tool_result", analyst.id, {"tool": "catalog.search_tables", "summary": _summarize(hits)})
                return hits

        knowledge_hits, table_hits = await asyncio.gather(branch_retrieve(), branch_search())

        lines: list[str] = [f"任务目标: {task.objective}", f"协作团队: {team_names}"]
        lines.append(f"[并行] {retriever.name}·知识检索 ∥ {analyst.name}·目录检索")
        lines.append(f"[{retriever.name}·知识检索] {_summarize(knowledge_hits)}")
        lines.append(f"[{analyst.name}·目录检索] {_summarize(table_hits)}")

        # 数据采样: 取目录检索命中的第一张表
        candidates = table_hits if isinstance(table_hits, list) else []
        if candidates:
            await emit(
                session, "tool_call", analyst.id,
                {"tool": "data.query_table", "args": {"table_id": candidates[0]["table_id"], "limit": 5}},
            )
            resp = await execute_tool(
                session, "data.query_table",
                {"table_id": candidates[0]["table_id"], "limit": 5, "actor": f"agent:{analyst.name}", "role": "analyst"},
            )
            if resp.get("ok"):
                await emit(session, "tool_result", analyst.id, {"tool": "data.query_table", "summary": _summarize(resp["result"])})
                lines.append(f"[{analyst.name}·数据采样] {_summarize(resp['result'])}")
        else:
            await emit(session, "tool_call", analyst.id, {"tool": "data.query_table", "status": "skipped", "reason": "目录无匹配表"})
            lines.append(f"[{analyst.name}·数据采样] 目录中无匹配数据表, 跳过")

        # 主控汇总
        task.result = "\n".join(lines)
        task.status = "succeeded"
        task.finished_at = dt.datetime.now(dt.UTC)
        await session.commit()
        await emit(session, "completion", reporter.id, {"status": "succeeded"})
        await record_audit(f"agent:{reporter.name}", "task.run", "task", task.id, {"objective": task.objective})
    except Exception as exc:
        logger.exception("任务执行失败 task_id=%s", task.id)
        task.status = "failed"
        task.error = str(exc)
        task.finished_at = dt.datetime.now(dt.UTC)
        await session.commit()
        await emit(session, "error", main_agent.id, {"message": str(exc)})
    return task


def _summarize(result) -> str:
    """工具结果 -> 一行摘要."""
    if isinstance(result, list):
        if not result:
            return "无结果"
        if isinstance(result[0], dict) and "content" in result[0]:
            return f"命中 {len(result)} 条知识, 首条: {result[0]['content'][:80]}..."
        if isinstance(result[0], dict) and "table_name" in result[0]:
            names = ", ".join(r["table_name"] for r in result[:5])
            return f"匹配 {len(result)} 张表: {names}"
        return f"{len(result)} 条记录"
    if isinstance(result, dict):
        rows = result.get("rows")
        if rows is not None:
            masking = result.get("masking", {})
            note = " [已脱敏]" if masking.get("enabled") else ""
            return f"表 {result.get('table_name')} 采样 {len(rows)} 行{note}: {rows[:3]}"
        return str(result)[:200]
    return str(result)[:200]


async def get_task(session: AsyncSession, task_id: int) -> AgentTask:
    task = await session.get(AgentTask, task_id)
    if task is None:
        raise NotFoundError(f"任务不存在: {task_id}")
    return task


async def list_tasks(session: AsyncSession, limit: int = 50) -> list[AgentTask]:
    stmt = select(AgentTask).order_by(AgentTask.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())
