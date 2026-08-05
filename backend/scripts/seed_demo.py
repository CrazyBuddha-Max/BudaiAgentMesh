"""种子脚本: 创建演示数据源并执行一次采集, 再注册指标语义.

用法: .venv/bin/python -m scripts.seed_demo
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.access import models as access_models
from app.access.catalog import create_source
from app.access.ingestion import ingest_source
from app.access.schemas import SourceCreate
from app.core.database import SessionLocal, init_db
from app.knowledge import models as knowledge_models
from app.knowledge.schemas import MetricCreate
from app.knowledge.service import create_metric

_DEMO_METRICS: list[dict] = [
    {
        "name": "total_revenue",
        "display_name": "销售总额",
        "description": "订单金额合计 (单价 x 数量), 口径含全部订单状态",
        "measure": "unit_price * quantity",
        "aggregation": "sum",
        "dimensions": ["region", "product", "customer_name"],
        "unit": "元",
    },
    {
        "name": "order_count",
        "display_name": "订单笔数",
        "description": "订单明细行数 (含空值订单号行)",
        "measure": "*",
        "aggregation": "count",
        "dimensions": ["region", "product"],
        "unit": "笔",
    },
    {
        "name": "avg_order_value",
        "display_name": "客单价",
        "description": "平均每笔订单金额 (单价 x 数量)",
        "measure": "unit_price * quantity",
        "aggregation": "avg",
        "dimensions": ["region"],
        "unit": "元",
    },
    {
        "name": "max_single_quantity",
        "display_name": "最大单笔数量",
        "description": "单笔订单最大购买件数",
        "measure": "quantity",
        "aggregation": "max",
        "dimensions": ["region", "product"],
        "unit": "件",
    },
    {
        "name": "region_product_count",
        "display_name": "区域商品组合数",
        "description": "区域 x 商品的去重组合数量 (用于组合覆盖分析)",
        "measure": "product",
        "aggregation": "count_distinct",
        "dimensions": ["region"],
        "unit": "个",
    },
]


async def main() -> None:
    await init_db()
    async with SessionLocal() as session:
        # 数据源与目录
        csv_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "data", "sample_orders.csv")
        )
        existing = await session.scalar(
            select(access_models.DataSource).where(access_models.DataSource.name == "订单演示数据")
        )
        if existing is None:
            source = await create_source(
                session,
                SourceCreate(
                    name="订单演示数据",
                    source_type="csv",
                    description="电商订单示例数据, 用于 M1 演示数据接入与目录生成",
                    file_path=csv_path,
                ),
            )
            print(f"数据源已创建: id={source.id} name={source.name}")
            run = await ingest_source(session, source.id)
            print(f"采集完成: run={run.id} status={run.status} tables={run.tables_found} message={run.message}")
        else:
            source = existing
            print(f"数据源已存在: id={source.id} (跳过采集)")

        # 指标语义
        table = await session.scalar(
            select(access_models.CatalogTable)
            .where(access_models.CatalogTable.source_id == source.id)
            .order_by(access_models.CatalogTable.id)
            .limit(1)
        )
        if table is None:
            print("[跳过] 目录中没有可绑定指标的表")
            return
        created = 0
        for item in _DEMO_METRICS:
            exists = await session.scalar(
                select(knowledge_models.MetricDefinition).where(
                    knowledge_models.MetricDefinition.name == item["name"]
                )
            )
            if exists is not None:
                continue
            await create_metric(
                session,
                MetricCreate(
                    name=item["name"],
                    display_name=item["display_name"],
                    description=item["description"],
                    table_id=table.id,
                    measure=item["measure"],
                    aggregation=item["aggregation"],
                    dimensions=item["dimensions"],
                    unit=item["unit"],
                    owner="admin",
                ),
            )
            created += 1
        print(f"指标已注册: {created} 个 (绑定表 {table.schema_name}.{table.table_name})")


if __name__ == "__main__":
    asyncio.run(main())
