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


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    await init_db()
    yield


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
