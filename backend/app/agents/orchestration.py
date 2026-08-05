"""编排引擎 (M2 起步): 单 Agent 顺序流水线.

流程: 目标解析 -> 知识检索 -> 目录检索 -> 数据采样 -> 结果组装.
M3 将升级为多 Agent DAG (并行/层级/辩论) + 消息总线 (Kafka).
"""
import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import Agent, AgentEvent, AgentTask
from app.agents.tools import execute_tool
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger

logger = get_logger(__name__)

# 编排步骤: (名称, 工具名, 参数构造)
_STEPS = [
    ("知识检索", "knowledge.retrieve", lambda obj: {"query": obj, "top_k": 3}),
    ("目录检索", "catalog.search_tables", lambda obj: {"keyword": obj[:32]}),
    ("数据采样", "data.query_table", None),  # 动态确定 table_id
]


async def get_agent(session: AsyncSession, agent_id: int) -> Agent:
    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise NotFoundError(f"Agent 不存在: {agent_id}")
    return agent


async def create_task(
    session: AsyncSession, agent_id: int, objective: str, title: str | None = None
) -> AgentTask:
    await get_agent(session, agent_id)
    task = AgentTask(agent_id=agent_id, objective=objective, title=title or objective[:40], status="pending")
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def run_task(session: AsyncSession, task_id: int) -> AgentTask:
    """执行任务: 依次调用工具, 事件全量留痕, 结果可回溯."""
    task = await get_task(session, task_id)
    agent = await get_agent(session, task.agent_id)

    async def emit(event_type: str, payload: dict | None = None) -> None:
        session.add(AgentEvent(task_id=task.id, agent_id=agent.id, event_type=event_type, payload=payload))
        await session.commit()

    task.status = "running"
    task.error = None
    await session.commit()
    await emit("task_started", {"objective": task.objective, "agent": agent.name})

    try:
        plan = _plan(task.objective)
        await emit("plan", {"steps": [p[1] for p in plan]})
        lines: list[str] = [f"任务目标: {task.objective}"]

        for label, tool_name, args_fn in plan:
            args = args_fn(task.objective) if args_fn else {}
            # 数据采样步骤: 用目录检索结果中的第一张表
            if tool_name == "data.query_table":
                tables = await execute_tool(session, "catalog.search_tables", {"keyword": task.objective[:32]})
                candidates = tables.get("result", [])
                if not candidates:
                    await emit("tool_call", {"tool": tool_name, "status": "skipped", "reason": "目录中无匹配表"})
                    lines.append(f"[{label}] 目录中无匹配数据表, 跳过采样")
                    continue
                args = {"table_id": candidates[0]["table_id"], "limit": 5}

            await emit("tool_call", {"tool": tool_name, "args": args})
            resp = await execute_tool(session, tool_name, args)
            if not resp.get("ok"):
                raise RuntimeError(f"工具 {tool_name} 失败: {resp.get('error')}")
            result = resp["result"]
            await emit("tool_result", {"tool": tool_name, "summary": _summarize(result)})
            lines.append(f"[{label}] {_summarize(result)}")

        task.result = "\n".join(lines)
        task.status = "succeeded"
        task.finished_at = dt.datetime.now(dt.UTC)
        await session.commit()
        await emit("completion", {"status": "succeeded"})
    except Exception as exc:
        logger.exception("任务执行失败 task_id=%s", task.id)
        task.status = "failed"
        task.error = str(exc)
        task.finished_at = dt.datetime.now(dt.UTC)
        await session.commit()
        await emit("error", {"message": str(exc)})
    return task


def _plan(objective: str) -> list:
    """目标 -> 步骤 (M2 固定流水线; M3 由规划器动态分解)."""
    return [s for s in _STEPS]


def _summarize(result) -> str:
    """工具结果 -> 一行摘要, 保证结果文本可控."""
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
            return f"表 {result.get('table_name')} 采样 {len(rows)} 行: {rows[:3]}"
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
