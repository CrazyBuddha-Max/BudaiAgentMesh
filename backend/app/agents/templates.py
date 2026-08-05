"""Agent 模板市场 (M4): 预置角色模板, 一键创建专业化 Agent."""
from dataclasses import dataclass


@dataclass
class AgentTemplate:
    key: str
    name: str
    description: str
    capabilities: list[str]


AGENT_TEMPLATES: list[AgentTemplate] = [
    AgentTemplate(
        key="analyst-assistant",
        name="数据分析助手",
        description="主控型: 检索业务口径 + 定位数据表 + 采样分析, 适合经营分析场景",
        capabilities=["knowledge_retrieval", "data_access", "report_draft"],
    ),
    AgentTemplate(
        key="knowledge-retriever",
        name="知识检索员",
        description="专注语义检索企业知识库, 返回口径说明与相关文档",
        capabilities=["knowledge_retrieval"],
    ),
    AgentTemplate(
        key="data-analyst",
        name="数据分析员",
        description="专注数据访问: 定位数据表、采样样例、聚合查询",
        capabilities=["data_access"],
    ),
    AgentTemplate(
        key="report-writer",
        name="报告撰写员",
        description="汇聚多方结果, 生成结构化经营报告",
        capabilities=["report_draft"],
    ),
    AgentTemplate(
        key="security-auditor",
        name="安全审计员",
        description="审阅数据访问与脱敏策略, 输出合规检查结论",
        capabilities=["audit_review"],
    ),
]


def get_template(key: str) -> AgentTemplate:
    for template in AGENT_TEMPLATES:
        if template.key == key:
            return template
    raise KeyError(f"未知 Agent 模板: {key}")


def templates_out() -> list[dict]:
    return [
        {"key": t.key, "name": t.name, "description": t.description, "capabilities": t.capabilities}
        for t in AGENT_TEMPLATES
    ]
