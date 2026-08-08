"""认证与授权: JWT 签发 / 内置账号 / RBAC 依赖.

M1 阶段以内置账号演示 RBAC; M5 将接入 SSO/OAuth2.0 与 ABAC 策略引擎.
"""
import datetime as dt
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.core.config import settings
from app.core.exceptions import AuthError, ForbiddenError

ROLE_LEVELS = {"viewer": 1, "analyst": 2, "admin": 3}

_bearer = HTTPBearer(auto_error=False)


class TokenPayload(BaseModel):
    sub: str
    role: str
    tenant: str = "default"
    exp: dt.datetime


class CurrentUser(BaseModel):
    username: str
    role: str
    tenant: str = "default"  # M6 多租户: 资源隔离维度, 旧 token 缺省归 default

    @property
    def level(self) -> int:
        return ROLE_LEVELS.get(self.role, 0)


def _builtin_users() -> dict[str, tuple[str, str, str]]:
    """解析内置账号: 用户名 -> (密码, 角色, 租户).

    兼容两种格式: username:password:role (M1~M5, 归 default 租户)
                     username:password:role:tenant (M6 多租户)
    """
    users: dict[str, tuple[str, str, str]] = {}
    for item in settings.builtin_users.split(","):
        parts = item.strip().split(":")
        if len(parts) == 3:
            users[parts[0]] = (parts[1], parts[2], "default")
        elif len(parts) == 4:
            users[parts[0]] = (parts[1], parts[2], parts[3])
    return users


def authenticate(username: str, password: str) -> CurrentUser:
    users = _builtin_users()
    record = users.get(username)
    if record is None or record[0] != password:
        raise AuthError("用户名或密码错误")
    return CurrentUser(username=username, role=record[1], tenant=record[2])


def create_token(user: CurrentUser) -> str:
    now = dt.datetime.now(dt.UTC)
    payload = TokenPayload(
        sub=user.username,
        role=user.role,
        tenant=user.tenant,
        exp=now + dt.timedelta(minutes=settings.jwt_expire_minutes),
    )
    return jwt.encode(payload.model_dump(mode="python"), settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _decode_token(token: str) -> CurrentUser:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return CurrentUser(
            username=payload["sub"],
            role=payload["role"],
            tenant=payload.get("tenant", "default"),  # 旧 token 无 tenant 声明, 归 default
        )
    except jwt.PyJWTError as exc:
        raise AuthError("令牌无效或已过期") from exc


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    if credentials is None or not credentials.credentials:
        raise AuthError("缺少认证令牌")
    return _decode_token(credentials.credentials)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def require_role(min_role: str):
    """角色门槛: viewer < analyst < admin."""

    def checker(user: CurrentUserDep) -> CurrentUser:
        if user.level < ROLE_LEVELS.get(min_role, 0):
            raise ForbiddenError(f"需要 {min_role} 及以上角色")
        return user

    return checker


AdminDep = Annotated[CurrentUser, Depends(require_role("admin"))]
AnalystDep = Annotated[CurrentUser, Depends(require_role("analyst"))]
