"""种子脚本: 创建演示数据源 + 知识文档 + 演示 Agent, 并执行采集与入库.

用法: .venv/bin/python -m scripts.seed_demo
"""
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.access.catalog import create_source
from app.access.ingestion import ingest_source
from app.access.models import CatalogTable, DataSource
from app.access.schemas import SourceCreate
from app.core.database import SessionLocal, init_db
from app.knowledge.models import KnowledgeDoc
from app.knowledge.service import ingest_document


def _remap_for_cleanup(path: str) -> str:
    """清理场景的跨平台路径归一 (与连接器逻辑一致)."""
    import re

    m = re.match(r"^/mnt/([a-zA-Z])/(.*)$", path)
    if m:
        drive, rest = m.group(1), m.group(2)
        return f"{drive.upper()}:\\{rest}"
    return path


async def main() -> None:
    await init_db()
    async with SessionLocal() as session:
        from sqlalchemy import select

        # 0. 清理测试垃圾源: file_path 指向系统临时目录的 CSV 源 (测试遗留) 自动删除
        _tmp = os.path.realpath(tempfile.gettempdir())
        rows = (await session.execute(select(DataSource))).scalars().all()
        pruned = 0
        for src in rows:
            if src.source_type == "csv" and src.file_path:
                resolved = os.path.abspath(_remap_for_cleanup(src.file_path))
                if resolved.startswith(_tmp) and src.name != "订单演示数据":
                    await session.delete(src)
                    pruned += 1
        if pruned:
            await session.commit()
            print(f"已清理 {pruned} 个测试遗留数据源 (临时目录)")

        # 1. 订单演示数据源 (幂等: 已存在则仅修复路径)
        csv_rel = os.path.join("data", "sample_orders.csv")
        existing = (
            await session.execute(select(DataSource).where(DataSource.name == "订单演示数据"))
        ).scalar_one_or_none()
        if existing is None:
            source = await create_source(
                session,
                SourceCreate(
                    name="订单演示数据",
                    source_type="csv",
                    description="电商订单示例数据, 用于 M1 演示数据接入与目录生成",
                    file_path=csv_rel,
                ),
            )
        else:
            source = existing
            if source.file_path != csv_rel:
                source.file_path = csv_rel
                await session.commit()
        run = await ingest_source(session, source.id)
        print(f"数据源: {source.name} 采集 {run.status} tables={run.tables_found}")

        # 2. 业务指标口径知识文档 (幂等: 同名文档跳过)
        md_name = "sample_knowledge.md"
        doc_exists = (
            await session.execute(select(KnowledgeDoc).where(KnowledgeDoc.file_name == md_name))
        ).scalar_one_or_none()
        if doc_exists is None:
            md_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "sample_knowledge.md"))
            with open(md_path, "rb") as f:
                doc = await ingest_document(session, md_name, f.read())
            print(f"知识文档: {doc.title} status={doc.status} chunks={doc.chunk_count}")
        else:
            print(f"知识文档: {doc_exists.title} 已存在, 跳过")

        # 3. 演示 Agent 团队 (M3 多 Agent 协作)
        from sqlalchemy import select

        from app.agents.models import Agent

        TEAM = [
            Agent(
                name="数据分析助手",
                description="主控: 面向经营分析, 检索业务口径知识, 定位数据表并采样",
                capabilities=["knowledge_retrieval", "data_access", "report_draft"],
                tools=[],
                status="active",
            ),
            Agent(
                name="知识检索员",
                description="专注语义检索企业知识库, 返回口径说明与相关文档",
                capabilities=["knowledge_retrieval"],
                tools=[],
                status="active",
            ),
            Agent(
                name="数据分析员",
                description="专注数据访问: 定位数据表并采样样例数据",
                capabilities=["data_access"],
                tools=[],
                status="active",
            ),
        ]
        for agent in TEAM:
            exists = (await session.execute(select(Agent).where(Agent.name == agent.name))).scalar_one_or_none()
            if exists is None:
                session.add(agent)
                await session.commit()
                print(f"Agent: {agent.name} 已注册")
            else:
                print(f"Agent: {agent.name} 已存在, 跳过")

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
