"""知识沉淀层 ORM 模型 (M2 起步: 指标语义层)."""
import datetime as dt

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.access.models import CatalogTable
from app.core.database import Base

AGGREGATIONS = ("sum", "avg", "count", "min", "max", "count_distinct")


class MetricDefinition(Base):
    """指标定义: 统一口径, 绑定物理表, 可执行查询.

    measure 为度量表达式 (如 `unit_price * quantity`), aggregation 决定聚合方式;
    dimensions 声明允许下钻的维度列, default_filters 固化口径条件 (如排除取消订单).
    """

    __tablename__ = "metric_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)  # snake_case 机器名
    display_name: Mapped[str] = mapped_column(String(128))  # 中文名
    description: Mapped[str] = mapped_column(Text, default="")  # 口径定义
    table_id: Mapped[int] = mapped_column(ForeignKey("catalog_tables.id", ondelete="CASCADE"), index=True)
    measure: Mapped[str] = mapped_column(String(255))  # 度量表达式
    aggregation: Mapped[str] = mapped_column(String(32), default="sum")  # sum/avg/count/min/max/count_distinct
    dimensions: Mapped[list] = mapped_column(JSON, default=list)  # 允许下钻的维度列
    default_filters: Mapped[list] = mapped_column(JSON, default=list)  # 口径条件 [{column,op,value}]
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 元/件/%
    owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active/archived
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    table: Mapped[CatalogTable] = relationship()

    @property
    def expression(self) -> str:
        """可读表达式: AGG(measure)."""
        inner = "*" if self.measure.strip() == "*" else self.measure
        return f"{self.aggregation.upper()}({inner})"
