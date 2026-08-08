"""指标语义层 ORM 模型: 统一口径的指标定义."""
import datetime as dt

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

AGGREGATIONS = ("sum", "avg", "count", "min", "max", "count_distinct")


class MetricDefinition(Base):
    """指标定义: 口径即契约, 绑定目录表与度量表达式."""

    __tablename__ = "metric_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), default="default", index=True)  # M7 多租户
    display_name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("catalog_tables.id", ondelete="CASCADE"), index=True)
    measure: Mapped[str] = mapped_column(String(255))  # 度量表达式, 如 unit_price * quantity
    aggregation: Mapped[str] = mapped_column(String(32))  # sum/avg/count/min/max/count_distinct
    dimensions: Mapped[list[str]] = mapped_column(JSON, default=list)  # 允许下钻的维度列
    default_filters: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active/archived
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
