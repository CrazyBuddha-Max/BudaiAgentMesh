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

    # M7: 解析模型提供方 (Agent 绑定优先, 否则默认; 无配置则模板降级)
    provider = None
    try:
        from app.agents.llm import get_default_provider, get_provider

        if main_agent.llm_provider_id:
            provider = await get_provider(session, main_agent.llm_provider_id)
        else:
            provider = await get_default_provider(session)
    except Exception:
        provider = None

    llm_mode = provider is not None and provider.enabled

    try:
        # ---- LLM 规划 (真实调用, 失败降级为固定步骤) ----
        steps: list[str] = ["knowledge.retrieve", "catalog.search_tables", "data.query_table"]
        search_keyword: str = task.objective  # 目录检索关键词 (LLM 规划产出, 降级用完整目标)
        if llm_mode:
            try:
                from app.agents.llm import chat_completion

                plan = await chat_completion(
                    provider,
                    [
                        {"role": "system", "content": (
                            "你是任务规划器。根据用户目标输出 JSON: "
                            "{\"steps\": [从 knowledge.retrieve(知识检索), catalog.search_tables(目录检索), "
                            "data.query_table(数据采样) 中选 1-5 个], "
                            "\"keyword\": 用于目录检索的简短关键词 (1-3 个英文或中文词, 如 \"order\" 或 \"订单\")}。"
                            "只输出 JSON。"
                        )},
                        {"role": "user", "content": task.objective},
                    ],
                    temperature=0,
                    max_tokens=200,
                )
                import json
                import re

                m = re.search(r"\{[^}]*\}", plan)
                if m:
                    parsed = json.loads(m.group(0))
                    if isinstance(parsed, dict):
                        if isinstance(parsed.get("steps"), list) and parsed["steps"]:
                            steps = [str(s) for s in parsed["steps"]][:5]
                        kw = str(parsed.get("keyword", "")).strip()
                        if kw and kw != "None":
                            search_keyword = kw
                await emit(session, "llm.plan", main_agent.id, {"provider": provider.name, "model": provider.model, "steps": steps, "keyword": search_keyword})
            except Exception as exc:
                await emit(session, "llm.plan", main_agent.id, {"provider": provider.name, "error": str(exc)[:200], "fallback": True})

        await emit(
            session, "plan", main_agent.id,
            {"steps": steps, "llm": llm_mode},
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
                await emit(bs, "tool_call", analyst.id, {"tool": "catalog.search_tables", "args": {"keyword": search_keyword}})
                resp = await execute_tool(bs, "catalog.search_tables", {"keyword": search_keyword})
                if not resp.get("ok"):
                    raise RuntimeError(f"目录检索失败: {resp.get('error')}")
                hits = resp["result"]
                await emit(bs, "tool_result", analyst.id, {"tool": "catalog.search_tables", "summary": _summarize(hits)})
                return hits

        knowledge_hits, table_hits = await asyncio.gather(branch_retrieve(), branch_search())

        # 数据采样: 取目录检索命中的第一张表 (采样更多行供 LLM 完整分析)
        candidates = table_hits if isinstance(table_hits, list) else []
        sample_rows_result = None
        if candidates:
            await emit(
                session, "tool_call", analyst.id,
                {"tool": "data.query_table", "args": {"table_id": candidates[0]["table_id"], "limit": 100}},
            )
            resp = await execute_tool(
                session, "data.query_table",
                {"table_id": candidates[0]["table_id"], "limit": 100, "actor": f"agent:{analyst.name}", "role": "analyst"},
            )
            if resp.get("ok"):
                sample_rows_result = resp["result"]
                await emit(session, "tool_result", analyst.id, {"tool": "data.query_table", "summary": _summarize(resp["result"])})
        else:
            await emit(session, "tool_call", analyst.id, {"tool": "data.query_table", "status": "skipped", "reason": "目录无匹配表"})

        # 主控汇总: LLM 生成结论 (真实调用, 失败降级为结构化拼接)
        lines: list[str] = [f"任务目标: {task.objective}", f"协作团队: {team_names}"]
        lines.append(f"[并行] {retriever.name}·知识检索 ∥ {analyst.name}·目录检索")
        lines.append(f"[{retriever.name}·知识检索] {_summarize(knowledge_hits)}")
        lines.append(f"[{analyst.name}·目录检索] {_summarize(table_hits)}")
        sampling_line = "目录中无匹配数据表, 跳过"
        if sample_rows_result is not None:
            sampling_line = _summarize(sample_rows_result)
        lines.append(f"[{analyst.name}·数据采样] {sampling_line}")

        # 汇总上下文: 附上知识命中原文与采样数据, 让 LLM 能给出具体答案而非泛泛而谈
        llm_context = "\n".join(lines)
        knowledge_texts: list[str] = []
        for idx, hit in enumerate(knowledge_hits[:3]):
            content = hit.get("content") if isinstance(hit, dict) else getattr(hit, "content", "")
            if content:
                knowledge_texts.append(f"[知识{idx + 1}] {str(content)[:500]}")
        if knowledge_texts:
            llm_context += "\n\n=== 知识库命中原文 ===\n" + "\n".join(knowledge_texts)
        if sample_rows_result is not None:
            rows = sample_rows_result.get("rows", []) if isinstance(sample_rows_result, dict) else []
            if rows:
                import json as _json

                llm_context += "\n\n=== 数据表采样 ===\n" + _json.dumps(rows, ensure_ascii=False, default=str)[:6000]

        if llm_mode:
            try:
                from app.agents.llm import chat_completion

                answer = await chat_completion(
                    provider,
                    [
                        {"role": "system", "content": (
                            "你是数据分析助手。直接回答用户的问题, 给出具体、可操作的结论。"
                            "规则: 1) 必须基于提供的知识原文与数据采样作答, 引用具体数字/口径; "
                            "2) 若数据不足, 明确说出缺少什么, 但先用已有知识给出最可能的答案; "
                            "3) 输出格式: 【结论】一段话, 【依据】要点列表, 【局限与建议】. "
                            "用中文, 200 字以内, 不得回复'无法生成结论'之类回避性文字。"
                        )},
                        {"role": "user", "content": llm_context},
                    ],
                )
                task.result = f"【LLM 汇总 · {provider.name}/{provider.model}】\n\n{answer}"
                await emit(session, "llm.summary", reporter.id, {"provider": provider.name, "model": provider.model})
            except Exception as exc:
                task.result = "\n".join(lines)
                await emit(session, "llm.summary", reporter.id, {"error": str(exc)[:200], "fallback": True})
        else:
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
