"""API 路由聚合."""
from fastapi import APIRouter

from app.api import access, feedback, health, knowledge, security

api_router = APIRouter()
api_router.include_router(health.router, tags=["system"])
api_router.include_router(security.router, prefix="/security", tags=["security"])
api_router.include_router(access.router, prefix="/access", tags=["access"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["knowledge"])
api_router.include_router(feedback.router, prefix="/feedback", tags=["feedback"])
