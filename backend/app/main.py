"""BudaiAgentMesh 后端应用入口."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import api_router
from app.core.config import settings
from app.core.database import init_db
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.feedback.metrics import MetricsMiddleware

# M5: 完整 MCP Server (streamable-http, 供外部 Agent 客户端调用)
try:
    from app.agents.mcp_server import mcp

    mcp_app = mcp.http_app()
except ImportError:  # fastmcp 未安装时优雅降级
    mcp_app = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    await init_db()
    from app.agents.bus import bus

    if hasattr(bus, "start"):  # 进程内总线启动后台 Worker
        await bus.start()
    if mcp_app is not None:  # MCP 服务端生命周期: 初始化任务组
        async with mcp_app.router.lifespan_context(mcp_app):
            yield
    else:
        yield
    if hasattr(bus, "stop"):
        await bus.stop()


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description="面向 AI Agent 生态的数据操作系统: 接入 / 知识 / 协同 / 安全 / 反馈",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(MetricsMiddleware)

register_exception_handlers(app)

app.include_router(api_router, prefix=settings.api_prefix)

if mcp_app is not None:
    app.mount("/mcp", mcp_app)
