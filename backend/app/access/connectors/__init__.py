"""连接器市场: 统一 SourceContract 与注册表."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ColumnProfile:
    """字段级质量画像 (Schema 注册 + 质量初检结果)."""

    name: str
    data_type: str
    is_nullable: bool = True
    is_primary_key: bool = False
    null_rate: float = 0.0
    distinct_ratio: float = 0.0
    sample_values: list[Any] = field(default_factory=list)


@dataclass
class TableProfile:
    """表级画像."""

    schema_name: str
    table_name: str
    row_count: int
    columns: list[ColumnProfile] = field(default_factory=list)


class SourceContract(ABC):
    """数据源契约: 所有连接器必须实现, Agent 只面向契约编程.

    设计原则 (见架构文档 ADR-2): 先定义契约再实现, 契约即承诺.
    """

    source_type: str = "base"

    def __init__(self, **params: Any) -> None:
        self.params = params

    @abstractmethod
    async def test_connection(self) -> None:
        """校验连接可用性, 失败抛出异常."""

    @abstractmethod
    async def discover_schema(self) -> list[TableProfile]:
        """发现并采样表结构, 附带质量初检画像."""

    @abstractmethod
    async def sample_rows(self, table_name: str, limit: int = 10) -> list[dict]:
        """读取表数据样例 (供 Agent 数据工具调用)."""

    async def detect_changes(self, previous_watermark: str | None) -> dict:
        """增量检测 (M6): 默认全量重采, 支持指纹的连接器 (如 CSV) 覆盖实现.

        返回 {"changed": bool, "watermark": str|None, "detail": str}.
        """
        return {"changed": True, "watermark": None, "detail": "全量采集"}

    async def query_aggregate(
        self,
        table: str,
        aggregation: str,
        measure: str,
        group_by: list[str] | None = None,
        filters: list[dict] | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """执行聚合查询 (指标语义层调用): SELECT AGG(measure) [GROUP BY dims].

        返回行列表: 无 group_by 时为 [{"value": ...}];
        有 group_by 时为 [{"<维度列>": ..., "value": ...}, ...].
        """
        raise NotImplementedError(f"连接器 {self.source_type} 暂不支持指标查询")

    async def close(self) -> None:
        """释放资源."""


class ConnectorRegistry:
    """连接器注册表: 类型 -> 契约实现."""

    def __init__(self) -> None:
        self._registry: dict[str, type[SourceContract]] = {}

    def register(self, cls: type[SourceContract]) -> None:
        self._registry[cls.source_type] = cls

    def get(self, source_type: str) -> type[SourceContract]:
        cls = self._registry.get(source_type)
        if cls is None:
            raise KeyError(f"未注册的连接器类型: {source_type}")
        return cls

    def available(self) -> list[str]:
        return sorted(self._registry.keys())

    def build(self, source_type: str, params: dict[str, Any]) -> SourceContract:
        return self.get(source_type)(**params)


registry = ConnectorRegistry()


def register_connector(cls: type[SourceContract]) -> type[SourceContract]:
    """装饰器: 注册连接器实现."""
    registry.register(cls)
    return cls


# 导入即注册: 连接器市场仅包含已导入的模块
try:
    from app.access.connectors import csv as _csv  # noqa: F401
except ImportError:
    pass
try:
    from app.access.connectors import mysql as _mysql  # noqa: F401
except ImportError:
    pass
try:
    from app.access.connectors import postgres as _postgres  # noqa: F401
except ImportError:
    pass
