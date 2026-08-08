"""能力注册表 (M7): 智能体能力声明数据化.

设计: 能力在此集中声明 (code/中文名/说明/关联工具), 前端能力选择与编排分工均
动态读取本表 —— 新增能力只需在此加一行, 无需改动任何页面与编排代码;
新创建的 Agent 声明任意能力 (含注册表外的新能力) 时, 编排由 LLM 按团队能力
动态分工, 同样无需硬编码.
"""


class Capability:
    __slots__ = ("code", "description", "label", "tools")

    def __init__(self, code: str, label: str, description: str, tools: list[str] | None = None) -> None:
        self.code = code
        self.label = label
        self.description = description
        self.tools = tools or []


CAPABILITIES: list[Capability] = [
    Capability(
        "knowledge_retrieval",
        "知识检索",
        "语义检索企业知识库, 返回口径说明与相关文档",
        ["knowledge.retrieve"],
    ),
    Capability(
        "data_access",
        "数据访问",
        "定位数据表并采样数据",
        ["catalog.search_tables", "data.query_table"],
    ),
    Capability("report_draft", "报告撰写", "基于数据与知识撰写结构化报告"),
    Capability("audit_review", "审计复核", "审阅数据访问与脱敏策略, 输出合规检查结论"),
]


def capabilities_out() -> list[dict]:
    return [
        {"code": c.code, "label": c.label, "description": c.description, "tools": c.tools}
        for c in CAPABILITIES
    ]


def capability_label(code: str) -> str:
    for c in CAPABILITIES:
        if c.code == code:
            return c.label
    return code
