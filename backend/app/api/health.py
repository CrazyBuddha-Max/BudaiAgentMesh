"""健康检查与服务信息."""
from fastapi import APIRouter

from app import __version__
from app.core.config import settings

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": settings.app_name, "version": __version__}


@router.get("/")
async def root() -> dict:
    return {
        "name": settings.app_name,
        "version": __version__,
        "docs": "/docs",
        "layers": ["access", "knowledge", "agents", "security", "feedback"],
    }
