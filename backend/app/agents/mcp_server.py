"""完整 MCP Server (M5): 将数据能力暴露为标准 Model Context Protocol 端点.

挂载于 /mcp (streamable-http), 任何 MCP 客户端 (Claude Desktop / Cursor / 自定义 Agent)
均可发现并调用: 知识检索 / 目录检索 / 数据采样 / 指标查询.

安全: 所有数据输出按 analyst 角色脱敏策略执行; 标识符与表达式经白名单校验.
"""
import json
from typing import Any

from fastmcp.server import FastMCP

from app.core.database import SessionLocal

mcp = FastMCP(
    "budai-agent-mesh",
    instructions=(
        "BudaiAgentMesh 智能体数据中台: 提供企业数据目录检索、知识语义检索、"
        "数据采样与指标查询能力。所有数据输出已按脱敏策略处理, 禁止要求返回原始敏感字段。"
    ),
)


def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


@mcp.tool()
async def knowledge_retrieve(query: str, top_k: int = 3) -> str:
    """语义检索企业知识库, 返回与查询最相关的知识切块与相似度.

    Args:
        query: 检索意图, 如 '毛利率的计算口径'
        top_k: 返回条数 (1-10)
    """
    from app.knowledge.service import search

    top_k = max(1, min(top_k, 10))
    async with SessionLocal() as session:
        hits = await search(session, query, top_k=top_k)
    return _json(
        [{"score": h.score, "content": h.content[:400], "doc_id": h.doc_id} for h in hits]
    )


@mcp.tool()
async def catalog_search_tables(keyword: str) -> str:
    """在元数据目录中按关键词查找数据表.

    Args:
        keyword: 表名或描述关键词, 如 '订单'
    """
    from app.access.catalog import list_tables

    async with SessionLocal() as session:
        tables = await list_tables(session, keyword=keyword, limit=10)
    return _json(
        [
            {
                "table_id": t.id,
                "table_name": f"{t.schema_name}.{t.table_name}",
                "row_count": t.row_count,
                "quality_score": t.quality_score,
            }
            for t in tables
        ]
    )


@mcp.tool()
async def data_query_table(table_id: int, limit: int = 5) -> str:
    """读取数据表的样例数据 (按平台脱敏策略输出, 敏感列自动掩码).

    Args:
        table_id: 目录表 ID (用 catalog_search_tables 获取)
        limit: 采样行数 (1-20)
    """
    from app.access.catalog import query_table_rows

    limit = max(1, min(limit, 20))
    async with SessionLocal() as session:
        result = await query_table_rows(session, table_id, limit=limit, actor="mcp", role="analyst")
    return _json(result)


@mcp.tool()
async def metrics_query(metric_name: str = "", group_by: str = "") -> str:
    """查询指标 (按名称模糊匹配, 取首个), 可指定维度下钻.

    Args:
        metric_name: 指标名或显示名关键词, 如 '订单金额' 或 'order_amount'
        group_by: 逗号分隔的维度列, 如 'region,product' (仅限指标声明允许的维度)
    """
    from app.knowledge.metrics_schemas import MetricQueryRequest
    from app.knowledge.metrics_service import list_metrics, query_metric

    async with SessionLocal() as session:
        metrics = await list_metrics(session, keyword=metric_name or None)
        if not metrics:
            return _json({"error": f"未找到指标: {metric_name}"})
        metric = metrics[0]
        gb = [g.strip() for g in group_by.split(",") if g.strip()]
        try:
            result = await query_metric(
                session, metric.id, MetricQueryRequest(group_by=gb), actor="mcp", role="analyst"
            )
        except Exception as exc:  # 维度越权等业务错误转为可读信息
            return _json({"error": str(exc)})
    return _json(
        {
            "metric": result.metric.name,
            "expression": result.expression,
            "group_by": result.group_by,
            "rows": result.rows,
            "duration_ms": result.duration_ms,
        }
    )
