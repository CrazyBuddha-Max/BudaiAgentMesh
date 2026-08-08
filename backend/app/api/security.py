"""安全治理 API: 认证 / 审计日志 / 数据血缘 / 脱敏策略 / 列权限 / 生命周期."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import AuthError
from app.security.audit import list_audit_logs
from app.security.auth import (
    AdminDep,
    CurrentUser,
    CurrentUserDep,
    authenticate,
    create_token,
)
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
    await record_audit(user.username, "auth.login", "user", user.username, tenant=user.tenant)
    return LoginResponse(access_token=create_token(user), user=user)


@router.get("/me", response_model=CurrentUser)
async def me(user: CurrentUserDep) -> CurrentUser:
    return user


# ---------- SSO / OAuth2.0 (M6) ----------

@router.get("/sso/config")
async def sso_config() -> dict:
    """SSO 登录配置: 前端据此渲染登录按钮并跳转授权页."""
    from app.security.sso import SSO_PROVIDER

    if not SSO_PROVIDER.enabled:
        return {"enabled": False, "name": SSO_PROVIDER.config["provider_name"], "authorize_url": None}
    return {
        "enabled": True,
        "name": SSO_PROVIDER.config["provider_name"],
        "authorize_url": SSO_PROVIDER.build_authorize_url(),
    }


@router.get("/sso/callback", response_model=LoginResponse)
async def sso_callback(code: str, state: str, session: AsyncSession = SessionDep) -> LoginResponse:
    """OAuth2 回调: 校验 state -> 换码 -> 取用户 -> 签发本地 JWT."""
    from app.security.audit import record_audit
    from app.security.sso import SSO_PROVIDER

    if not SSO_PROVIDER.enabled:
        raise AuthError("SSO 未启用")
    if not SSO_PROVIDER.validate_state(state):
        raise AuthError("state 校验失败, 请重新发起 SSO 登录")
    user = await SSO_PROVIDER.exchange_code(code)
    await record_audit(user.username, "auth.sso_login", "user", user.username, tenant=user.tenant)
    return LoginResponse(access_token=create_token(user), user=user)


# ---------- 多租户 (M6) ----------

@router.get("/tenants")
async def tenants(user: AdminDep, session: AsyncSession = SessionDep) -> list[dict]:
    """租户列表 (admin): 多租户管理."""
    from app.security.tenant import list_tenants

    rows = await list_tenants(session)
    return [
        {"id": t.id, "code": t.code, "name": t.name, "status": t.status, "created_at": t.created_at.isoformat()}
        for t in rows
    ]


@router.post("/tenants", status_code=201)
async def create_tenant(
    payload: dict, user: AdminDep, session: AsyncSession = SessionDep
) -> dict:
    """新建租户 (admin): {code, name}."""
    from app.security.tenant import create_tenant

    tenant = await create_tenant(session, code=payload.get("code", ""), name=payload.get("name", ""))
    return {"id": tenant.id, "code": tenant.code, "name": tenant.name, "status": tenant.status}


@router.patch("/tenants/{code}")
async def patch_tenant(
    code: str, payload: dict, user: AdminDep, session: AsyncSession = SessionDep
) -> dict:
    """更新租户状态 (admin): {status: active|disabled}."""
    from app.security.tenant import set_tenant_status

    tenant = await set_tenant_status(session, code, payload.get("status", "active"))
    return {"id": tenant.id, "code": tenant.code, "name": tenant.name, "status": tenant.status}


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

    logs = await list_audit_logs(session, limit=limit, action=action, actor=actor, tenant=user.tenant)
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


# ---------- 细粒度列级权限 (M5) ----------

@router.get("/column-policies")
async def column_policies(
    user: CurrentUserDep,
    role: str | None = None,
    session: AsyncSession = SessionDep,
):
    """列级权限规则列表 (M5): 按角色禁止访问的列."""
    from app.security.acl import list_policies

    policies = await list_policies(session, role=role)
    return [
        {
            "id": p.id,
            "role": p.role,
            "table_id": p.table_id,
            "column_name": p.column_name,
            "created_by": p.created_by,
            "created_at": p.created_at.isoformat(),
        }
        for p in policies
    ]


@router.post("/column-policies", status_code=201)
async def create_column_policy(
    payload: dict, user: AdminDep, session: AsyncSession = SessionDep
):
    """新增列权限规则: {role, column_name, table_id?} (admin)."""
    from app.security.acl import create_policy

    policy = await create_policy(
        session,
        role=payload["role"],
        column_name=payload["column_name"],
        table_id=payload.get("table_id"),
        actor=user.username,
    )
    return {"id": policy.id, "role": policy.role, "table_id": policy.table_id, "column_name": policy.column_name}


@router.delete("/column-policies/{policy_id}", status_code=204)
async def remove_column_policy(
    policy_id: int, user: AdminDep, session: AsyncSession = SessionDep
) -> None:
    from app.security.acl import delete_policy

    await delete_policy(session, policy_id)


# ---------- 数据生命周期 (M5) ----------

@router.get("/lifecycle")
async def lifecycle(
    user: CurrentUserDep,
    session: AsyncSession = SessionDep,
):
    """数据生命周期视图: 保留期策略 + 状态 (M5)."""
    from app.security.retention import list_lifecycle, summary

    items = await list_lifecycle(session)
    return {"summary": await summary(session), "items": items}
