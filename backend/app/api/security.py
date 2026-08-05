"""安全治理 API: 认证 / 审计日志 / 数据血缘 / 脱敏策略."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.security.audit import list_audit_logs
from app.security.auth import CurrentUser, CurrentUserDep, authenticate, create_token
from app.security.lineage import build_lineage_graph
from app.security.masking import masking_policies

router = APIRouter()

SessionDep = Depends(get_session)


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: CurrentUser


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, session: AsyncSession = SessionDep) -> LoginResponse:
    from app.security.audit import record_audit

    user = authenticate(payload.username, payload.password)
    await record_audit(user.username, "auth.login", "user", user.username)
    return LoginResponse(access_token=create_token(user), user=user)


@router.get("/me", response_model=CurrentUser)
async def me(user: CurrentUserDep) -> CurrentUser:
    return user


# ---------- 审计 ----------

class AuditLogOut(BaseModel):
    id: int
    actor: str
    action: str
    target_type: str
    target_id: str | None = None
    detail: dict | None = None
    created_at: object = None


@router.get("/audit-logs")
async def audit_logs(
    user: CurrentUserDep,
    limit: int = Query(200, le=500),
    action: str | None = None,
    actor: str | None = None,
    session: AsyncSession = SessionDep,
):
    """审计日志: 谁在何时访问了什么 (M3)."""

    logs = await list_audit_logs(session, limit=limit, action=action, actor=actor)
    return [
        {
            "id": log.id,
            "actor": log.actor,
            "action": log.action,
            "target_type": log.target_type,
            "target_id": log.target_id,
            "detail": log.detail,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]


# ---------- 血缘 ----------

@router.get("/lineage")
async def lineage(
    user: CurrentUserDep,
    limit: int = Query(500, le=2000),
    session: AsyncSession = SessionDep,
):
    """数据血缘图: 源表 -> 指标 -> 任务 -> 结果 (M3)."""
    return await build_lineage_graph(session, limit)


# ---------- 脱敏策略 ----------

@router.get("/masking-policies")
async def masking_policies_endpoint(user: CurrentUserDep) -> list[dict]:
    """动态脱敏策略清单 (M3)."""
    return masking_policies()
