"""测试夹具: 固定 SQLite, 清理历史库, 全局初始化表结构."""
import os

os.environ["SQLITE_URL"] = "sqlite+aiosqlite:///./data/test_budai_mesh.db"
os.environ["DATABASE_URL"] = ""

os.makedirs("./data", exist_ok=True)
for leftover in ("./data/test_budai_mesh.db", "./data/test_budai_mesh.db-shm", "./data/test_budai_mesh.db-wal"):
    if os.path.exists(leftover):
        os.remove(leftover)

import pytest  # noqa: E402

from app.core.database import init_db  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
async def _prepare_db():
    await init_db()
    yield
