"""种子脚本: 创建演示数据源 + 知识文档 + 演示 Agent, 并执行采集与入库.

用法: .venv/bin/python -m scripts.seed_demo
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.access.catalog import create_source
from app.access.ingestion import ingest_source
from app.access.models import CatalogTable
from app.access.schemas import SourceCreate
from app.core.database import SessionLocal, init_db
from app.knowledge.service import ingest_document


async def main() -> None:
    await init_db()
    async with SessionLocal() as session:
        # 1. 订单演示数据源 + 采集
        csv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "sample_orders.csv"))
        source = await create_source(
            session,
            SourceCreate(
                name="订单演示数据",
                source_type="csv",
                description="电商订单示例数据, 用于 M1 演示数据接入与目录生成",
                file_path=csv_path,
            ),
        )
        run = await ingest_source(session, source.id)
        print(f"数据源: {source.name} 采集 {run.status} tables={run.tables_found}")

        # 2. 业务指标口径知识文档
        md_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "sample_knowledge.md"))
        with open(md_path, "rb") as f:
            doc = await ingest_document(session, "sample_knowledge.md", f.read())
        print(f"知识文档: {doc.title} status={doc.status} chunks={doc.chunk_count}")

        # 3. 演示 Agent
        from sqlalchemy import select

        from app.agents.models import Agent

        existing = (await session.execute(select(Agent).where(Agent.name == "数据分析助手"))).scalar_one_or_none()
        if existing is None:
            agent = Agent(
                name="数据分析助手",
                description="面向经营分析的演示 Agent: 检索业务口径知识, 定位数据表并采样",
                capabilities=["knowledge_retrieval", "data_access", "report_draft"],
                tools=[],
                status="active",
            )
            session.add(agent)
            await session.commit()
            print(f"Agent: {agent.name} 已注册")
        else:
            print(f"Agent: {existing.name} 已存在, 跳过")

        # 4. 演示指标 (指标语义层)
        from app.knowledge.metrics_models import MetricDefinition
        from app.knowledge.metrics_schemas import MetricCreate
        from app.knowledge.metrics_service import create_metric

        metric_exists = (
            await session.execute(
                select(MetricDefinition).where(MetricDefinition.name == "order_amount")
            )
        ).scalar_one_or_none()
        if metric_exists is None:
            table_row = (await session.execute(select(CatalogTable).limit(1))).scalar_one_or_none()
            if table_row is not None:
                metric = await create_metric(
                    session,
                    MetricCreate(
                        name="order_amount",
                        display_name="订单金额",
                        description="订单金额合计: 单价 x 数量, 覆盖全部订单状态",
                        table_id=table_row.id,
                        measure="unit_price * quantity",
                        aggregation="sum",
                        dimensions=["region", "product"],
                        unit="元",
                        owner="admin",
                    ),
                )
                print(f"指标: {metric.display_name} (sum(unit_price * quantity)) 已注册")
        else:
            print(f"指标: {metric_exists.display_name} 已存在, 跳过")


if __name__ == "__main__":
    asyncio.run(main())
