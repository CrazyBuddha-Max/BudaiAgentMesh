"""接入层 Pydantic 契约 (对外 API 模型)."""
import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class SourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="数据源名称")
    source_type: str = Field(..., description="连接器类型: postgres/mysql/csv")
    description: str | None = None
    host: str | None = None
    port: int | None = None
    database: str | None = None
    schema_name: str | None = "public"
    username: str | None = None
    password: str | None = None
    file_path: str | None = None


class SourceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    host: str | None = None
    port: int | None = None
    database: str | None = None
    schema_name: str | None = None
    username: str | None = None
    password: str | None = None
    file_path: str | None = None
    retention_days: int | None = None  # 生命周期保留期 (M5)


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source_type: str
    description: str | None = None
    host: str | None = None
    port: int | None = None
    database: str | None = None
    schema_name: str | None = None
    username: str | None = None
    file_path: str | None = None
    retention_days: int | None = None  # 生命周期保留期 (M5)
    status: str
    quality_score: float
    last_ingested_at: dt.datetime | None = None
    created_at: dt.datetime


class ColumnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    column_name: str
    data_type: str
    is_nullable: bool
    is_primary_key: bool
    null_rate: float
    distinct_ratio: float
    sample_values: list | None = None
    description: str | None = None


class TableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    schema_name: str
    table_name: str
    row_count: int
    quality_score: float
    description: str | None = None
    columns: list[ColumnOut] = []


class ConnectorInfo(BaseModel):
    type: str
    display_name: str
    description: str
    available: bool
    params: list[str]


class IngestResult(BaseModel):
    source_id: int
    run_id: int
    status: str
    tables_found: int
    message: str
