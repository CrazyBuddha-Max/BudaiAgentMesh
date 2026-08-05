"""工具注册中心 (MCP 雏形): 以 JSON Schema 暴露数据能力.

数据能力 = 数据资产上的标准操作, 供 Agent 以 Function Calling 方式调用.
M3 将升级为完整 MCP Server (stdio/streamable-http).
"""
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.access.catalog import list_tables, query_table_rows
from app.knowledge.service import search


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict
    handler: Callable[..., Any] = field(default=None, repr=False)


def _build_tools(session: AsyncSession) -> list[ToolSpec]:
    async def knowledge_retrieve(query: str, top_k: int = 3) -> list[dict]:
        hits = await search(session, query, top_k=top_k)
        return [{"score": h.score, "content": h.content, "doc_id": h.doc_id} for h in hits]

    async def catalog_search(keyword: str) -> list[dict]:
        tables = await list_tables(session, keyword=keyword, limit=10)
        return [
            {
                "table_id": t.id,
                "table_name": f"{t.schema_name}.{t.table_name}",
                "row_count": t.row_count,
                "quality_score": t.quality_score,
            }
            for t in tables
        ]

    async def data_query(table_id: int, limit: int = 10, actor: str | None = None, role: str | None = None) -> dict:
        return await query_table_rows(session, table_id, limit=limit, actor=actor, role=role)

    return [
        ToolSpec(
            name="knowledge.retrieve",
            description="语义检索企业知识库, 返回与查询最相关的知识切块与相似度",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索意图"},
                    "top_k": {"type": "integer", "minimum": 1, "maximum": 10},
                },
                "required": ["query"],
            },
            handler=knowledge_retrieve,
        ),
        ToolSpec(
            name="catalog.search_tables",
            description="在元数据目录中按关键词查找数据表",
            parameters={
                "type": "object",
                "properties": {"keyword": {"type": "string"}},
                "required": ["keyword"],
            },
            handler=catalog_search,
        ),
        ToolSpec(
            name="data.query_table",
            description="读取数据表的样例数据行",
            parameters={
                "type": "object",
                "properties": {
                    "table_id": {"type": "integer"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                "required": ["table_id"],
            },
            handler=data_query,
        ),
    ]


def get_tool_specs(session: AsyncSession) -> list[ToolSpec]:
    return _build_tools(session)


def tool_schemas(session: AsyncSession) -> list[dict]:
    return [
        {
            "name": t.name,
            "description": t.description,
            "parameters": t.parameters,
        }
        for t in _build_tools(session)
    ]


async def execute_tool(session: AsyncSession, name: str, args: dict) -> dict:
    for tool in _build_tools(session):
        if tool.name == name:
            result = await tool.handler(**args)
            return {"tool": name, "ok": True, "result": result}
    return {"tool": name, "ok": False, "error": f"未知工具: {name}"}
