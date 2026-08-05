"""观测 API: 运行指标."""
from fastapi import APIRouter

from app.feedback.metrics import snapshot
from app.security.auth import CurrentUserDep

router = APIRouter()


@router.get("/metrics")
async def metrics(user: CurrentUserDep) -> dict:
    return snapshot()
