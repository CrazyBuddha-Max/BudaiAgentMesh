"""知识沉淀层核心测试 (指标语义层): CRUD / RBAC / 可执行查询."""

import os
import shutil
import tempfile

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import init_db
from app.main import app

CSV_CONTENT = """order_id,customer_name,region,product,quantity,unit_price,status
1001,张三,华东,智能音箱,2,299.00,ok
1002,李四,华东,智能手表,1,1299.00,ok
1003,王五,华北,智能音箱,3,299.00,cancelled
1004,赵六,华南,无线耳机,5,199.00,ok
1005,钱七,华东,智能门锁,1,899.00,ok
"""


@pytest.fixture(scope="module")
def csv_file() -> str:
    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, "orders.csv")
    with open(path, "w", encoding="utf-8") as f:
        f.write(CSV_CONTENT)
    yield path
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module", autouse=True)
async def prepare_db():
    await init_db()
    yield


async def _client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def _login(client: AsyncClient, username: str = "admin", password: str = "admin123") -> str:
    resp = await client.post("/api/security/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
async def seeded_table_id(csv_file: str):
    """创建 CSV 数据源 -> 采集 -> 返回目录表 id."""
    async with await _client() as client:
        token = await _login(client)
        headers = _auth(token)
        resp = await client.post(
            "/api/access/sources",
            json={"name": "orders-metric", "source_type": "csv", "file_path": csv_file},
            headers=headers,
        )
        source_id = resp.json()["id"]
        await client.post(f"/api/access/sources/{source_id}/test", headers=headers)
        await client.post(f"/api/access/sources/{source_id}/ingest", headers=headers)
        resp = await client.get("/api/access/catalog/tables", headers=headers)
        table_id = resp.json()[0]["id"]
        yield table_id
        await client.delete(f"/api/access/sources/{source_id}", headers=headers)


async def _create_metric(client, token, table_id: int, **overrides) -> dict:
    payload = {
        "name": "total_revenue",
        "display_name": "销售总额",
        "description": "订单金额合计",
        "table_id": table_id,
        "measure": "unit_price * quantity",
        "aggregation": "sum",
        "dimensions": ["region", "product"],
        "unit": "元",
    }
    payload.update(overrides)
    resp = await client.post("/api/knowledge/metrics", json=payload, headers=_auth(token))
    return resp


@pytest.mark.anyio
async def test_metric_crud_flow(seeded_table_id: int):
    async with await _client() as client:
        token = await _login(client)
        headers = _auth(token)

        # 创建
        resp = await _create_metric(client, token, seeded_table_id)
        assert resp.status_code == 201, resp.text
        metric = resp.json()
        metric_id = metric["id"]
        assert metric["expression"] == "SUM(unit_price * quantity)"
        assert metric["table"]["table_name"] == "orders"
        assert metric["source"]["source_type"] == "csv"

        # 重复名拒绝
        resp = await _create_metric(client, token, seeded_table_id)
        assert resp.status_code == 400

        # 列表 + 关键词
        resp = await client.get("/api/knowledge/metrics", headers=headers)
        assert any(m["id"] == metric_id for m in resp.json())
        resp = await client.get("/api/knowledge/metrics", params={"keyword": "销售"}, headers=headers)
        assert any(m["id"] == metric_id for m in resp.json())

        # 详情
        resp = await client.get(f"/api/knowledge/metrics/{metric_id}", headers=headers)
        assert resp.json()["display_name"] == "销售总额"

        # 更新
        resp = await client.patch(
            f"/api/knowledge/metrics/{metric_id}",
            json={"unit": "万元", "aggregation": "avg"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["unit"] == "万元"
        assert resp.json()["aggregation"] == "avg"

        # 删除 (admin)
        resp = await client.delete(f"/api/knowledge/metrics/{metric_id}", headers=headers)
        assert resp.status_code == 204


@pytest.mark.anyio
async def test_metric_validation(seeded_table_id: int):
    async with await _client() as client:
        token = await _login(client)

        # 度量表达式引用未注册列
        resp = await _create_metric(client, token, seeded_table_id, measure="not_a_column * 2")
        assert resp.status_code == 400
        assert "未注册" in resp.json()["message"]

        # 维度未注册
        resp = await _create_metric(client, token, seeded_table_id, dimensions=["not_a_dim"])
        assert resp.status_code == 400

        # 非法表达式字符 (注入尝试)
        resp = await _create_metric(client, token, seeded_table_id, measure="unit_price; DROP TABLE x")
        assert resp.status_code == 400


@pytest.mark.anyio
async def test_metric_query_sum_groupby(seeded_table_id: int):
    async with await _client() as client:
        token = await _login(client)
        resp = await _create_metric(client, token, seeded_table_id)
        metric_id = resp.json()["id"]

        # 无维度: 总额 = 2*299 + 1*1299 + 3*299 + 5*199 + 1*899 = 598+1299+897+995+899 = 4688
        resp = await client.post(
            f"/api/knowledge/metrics/{metric_id}/query", json={}, headers=_auth(token)
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["expression"] == "SUM(unit_price * quantity)"
        assert body["rows"][0]["value"] == 4688.0

        # 按区域下钻: 华东 = 598+1299+899 = 2796, 华北 = 897, 华南 = 995
        resp = await client.post(
            f"/api/knowledge/metrics/{metric_id}/query",
            json={"group_by": ["region"]},
            headers=_auth(token),
        )
        rows = {r["region"]: r["value"] for r in resp.json()["rows"]}
        assert rows["华东"] == 2796.0
        assert rows["华北"] == 897.0
        assert rows["华南"] == 995.0

        # 非法维度 (不在指标 dimensions 内)
        resp = await client.post(
            f"/api/knowledge/metrics/{metric_id}/query",
            json={"group_by": ["customer_name"]},
            headers=_auth(token),
        )
        assert resp.status_code == 400

        # 过滤: status != cancelled -> 总金额 = 4688 - 897 = 3791
        resp = await client.post(
            f"/api/knowledge/metrics/{metric_id}/query",
            json={"filters": [{"column": "status", "op": "neq", "value": "cancelled"}]},
            headers=_auth(token),
        )
        assert resp.json()["rows"][0]["value"] == 3791.0

        # 清理
        await client.delete(f"/api/knowledge/metrics/{metric_id}", headers=_auth(token))


@pytest.mark.anyio
async def test_metric_query_avg_count_distinct(seeded_table_id: int):
    async with await _client() as client:
        token = await _login(client)

        # 客单价 avg = 4688 / 5 = 937.6
        resp = await _create_metric(
            client, token, seeded_table_id,
            name="avg_order_value", display_name="客单价",
            measure="unit_price * quantity", aggregation="avg",
        )
        avg_id = resp.json()["id"]
        resp = await client.post(f"/api/knowledge/metrics/{avg_id}/query", json={}, headers=_auth(token))
        assert resp.json()["rows"][0]["value"] == 937.6

        # count: 5 行
        resp = await _create_metric(
            client, token, seeded_table_id,
            name="order_count", display_name="订单笔数",
            measure="*", aggregation="count",
        )
        count_id = resp.json()["id"]
        resp = await client.post(f"/api/knowledge/metrics/{count_id}/query", json={}, headers=_auth(token))
        assert resp.json()["rows"][0]["value"] == 5

        # count_distinct: product 去重 = {智能音箱, 智能手表, 无线耳机, 智能门锁} = 4
        resp = await _create_metric(
            client, token, seeded_table_id,
            name="product_count", display_name="商品种类数",
            measure="product", aggregation="count_distinct",
        )
        dc_id = resp.json()["id"]
        resp = await client.post(f"/api/knowledge/metrics/{dc_id}/query", json={}, headers=_auth(token))
        assert resp.json()["rows"][0]["value"] == 4

        for mid in (avg_id, count_id, dc_id):
            await client.delete(f"/api/knowledge/metrics/{mid}", headers=_auth(token))


@pytest.mark.anyio
async def test_metric_rbac(seeded_table_id: int):
    async with await _client() as client:
        viewer = await _login(client, "viewer", "viewer123")
        analyst = await _login(client, "analyst", "analyst123")

        # viewer 可读不可写
        resp = await client.get("/api/knowledge/metrics", headers=_auth(viewer))
        assert resp.status_code == 200
        resp = await _create_metric(client, viewer, seeded_table_id)
        assert resp.status_code == 403

        # analyst 可创建, 不可删除
        resp = await _create_metric(client, analyst, seeded_table_id, name="analyst_metric")
        assert resp.status_code == 201
        metric_id = resp.json()["id"]
        resp = await client.delete(f"/api/knowledge/metrics/{metric_id}", headers=_auth(analyst))
        assert resp.status_code == 403

        # admin 可删除
        admin = await _login(client)
        resp = await client.delete(f"/api/knowledge/metrics/{metric_id}", headers=_auth(admin))
        assert resp.status_code == 204
