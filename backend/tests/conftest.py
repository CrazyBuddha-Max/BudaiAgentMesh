"""测试夹具: 在导入 app 前固定使用 SQLite, 并清理历史测试库."""
import os

os.environ["SQLITE_URL"] = "sqlite+aiosqlite:///./data/test_budai_mesh.db"
os.environ["DATABASE_URL"] = ""

os.makedirs("./data", exist_ok=True)
for leftover in ("./data/test_budai_mesh.db", "./data/test_budai_mesh.db-shm", "./data/test_budai_mesh.db-wal"):
    if os.path.exists(leftover):
        os.remove(leftover)
