"""指标语义层契约 (与前端 src/api/types.ts 对齐)."""
import datetime as dt

from pydantic import BaseModel, Field


class FilterRule(BaseModel):
    column: str
    op: str = Field(default="eq", description="eq/neq/gt/ge/lt/le/in/contains")
    value: object | None = None


class MetricCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    table_id: int
    measure: str = Field(..., description="度量表达式, 如 unit_price * quantity")
    aggregation: str = Field(default="sum")
    dimensions: list[str] = []
    default_filters: list[FilterRule] | None = None
    unit: str | None = None
    owner: str | None = None


class MetricQueryRequest(BaseModel):
    group_by: list[str] = []
    filters: list[FilterRule] | None = None
    limit: int = Field(default=100, ge=1, le=500)


class TableBrief(BaseModel):
    id: int
    schema_name: str
    table_name: str
    row_count: int
    quality_score: float


class SourceBrief(BaseModel):
    id: int
    name: str
    source_type: str


class MetricOut(BaseModel):
    id: int
    name: str
    display_name: str
    description: str | None = None
    table_id: int
    measure: str
    expression: str  # 与 measure 一致, 供前端展示
    aggregation: str
    dimensions: list[str] = []
    default_filters: list[dict] | None = None
    unit: str | None = None
    owner: str | None = None
    status: str
    created_at: dt.datetime
    updated_at: dt.datetime
    table: TableBrief | None = None
    source: SourceBrief | None = None


class MetricQueryResult(BaseModel):
    metric: MetricOut
    source: dict
    expression: str
    group_by: list[str]
    rows: list[dict]
    duration_ms: int
    executed_at: dt.datetime
