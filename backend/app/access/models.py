"""接入层 ORM 模型: 数据源 / 目录表 / 目录列 / 采集任务."""
import datetime as dt

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

CONNECTOR_TYPES = ("postgres", "mysql", "csv")


class DataSource(Base):
    """数据源: 统一接入层的注册单元."""

    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    source_type: Mapped[str] = mapped_column(String(32), index=True)  # postgres/mysql/csv
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 连接参数 (secret 字段以密文存储, 绝不返回前端)
    host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    database: Mapped[str | None] = mapped_column(String(128), nullable=True)
    schema_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    password_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/active/error
    quality_score: Mapped[float] = mapped_column(default=0.0)
    last_ingested_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    tables: Mapped[list["CatalogTable"]] = relationship(
        back_populates="source", cascade="all, delete-orphan", lazy="selectin"
    )


class CatalogTable(Base):
    """目录表: Schema 注册后的物理表."""

    __tablename__ = "catalog_tables"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"), index=True)
    schema_name: Mapped[str] = mapped_column(String(128), default="public")
    table_name: Mapped[str] = mapped_column(String(255), index=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    quality_score: Mapped[float] = mapped_column(default=0.0)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    source: Mapped[DataSource] = relationship(back_populates="tables")
    columns: Mapped[list["CatalogColumn"]] = relationship(
        back_populates="table", cascade="all, delete-orphan", lazy="selectin"
    )


class CatalogColumn(Base):
    """目录列: 字段级元数据 + 质量初检结果."""

    __tablename__ = "catalog_columns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("catalog_tables.id", ondelete="CASCADE"), index=True)
    column_name: Mapped[str] = mapped_column(String(255))
    data_type: Mapped[str] = mapped_column(String(64))
    is_nullable: Mapped[bool] = mapped_column(default=True)
    is_primary_key: Mapped[bool] = mapped_column(default=False)
    null_rate: Mapped[float] = mapped_column(default=0.0)
    distinct_ratio: Mapped[float] = mapped_column(default=0.0)
    sample_values: Mapped[list | None] = mapped_column(JSON, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    table: Mapped[CatalogTable] = relationship(back_populates="columns")


class IngestionRun(Base):
    """采集任务记录: 可观测、可回溯."""

    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running/success/failed
    tables_found: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
