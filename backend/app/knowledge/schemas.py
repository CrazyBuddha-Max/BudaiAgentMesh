"""知识沉淀层 Pydantic 契约 (指标语义层)."""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Aggregation = Literal["sum", "avg", "count", "min", "max", "count_distinct"]
FilterOp = Literal["eq", "neq", "gt", "ge", "lt", "le", "in", "contains"]


class FilterRule(BaseModel):
    """指标口径条件 / 查询过滤条件."""

    column: str
    op: FilterOp = "eq"
    value: Any = None


class MetricCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_]*$")
    display_name: str = Field(min_length=1, max_length=128)
    description: str = ""
    table_id: int
    measure: str = Field(min_length=1, max_length=255)
    aggregation: Aggregation = "sum"
    dimensions: list[str] = Field(default_factory=list)
    default_filters: list[FilterRule] = Field(default_factory=list)
    unit: str | None = None
    owner: str | None = None
    status: Literal["active", "archived"] = "active"


class MetricUpdate(BaseModel):
    display_name: str | None = None
    description: str | None = None
    measure: str | None = None
    aggregation: Aggregation | None = None
    dimensions: list[str] | None = None
    default_filters: list[FilterRule] | None = None
    unit: str | None = None
    owner: str | None = None
    status: Literal["active", "archived"] | None = None


class MetricTableInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    schema_name: str
    table_name: str
    row_count: int
    quality_score: float


class MetricSourceInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source_type: str


class MetricOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    display_name: str
    description: str
    table_id: int
    measure: str
    aggregation: str
    dimensions: list[str]
    default_filters: list[dict]
    unit: str | None
    owner: str | None
    status: str
    created_at: Any
    updated_at: Any
    expression: str
    table: MetricTableInfo | None = None
    source: MetricSourceInfo | None = None


class MetricQueryRequest(BaseModel):
    """执行指标查询: 下钻维度 + 临时过滤条件."""

    group_by: list[str] = Field(default_factory=list, max_length=8)
    filters: list[FilterRule] = Field(default_factory=list)
    limit: int = Field(default=100, ge=1, le=1000)


class MetricQueryResult(BaseModel):
    metric: MetricOut
    source: dict
    expression: str
    group_by: list[str]
    rows: list[dict[str, Any]]
    duration_ms: float
    executed_at: str
