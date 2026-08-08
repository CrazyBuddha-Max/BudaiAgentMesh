"""SSO / OAuth2.0 授权码登录 (M6): 通用 OIDC 兼容实现.

流程: 前端跳 authorize_url?state=... -> IdP 授权后回跳 /callback?code&state
      -> 后端用 code 换 access_token -> 取 userinfo -> 映射角色 -> 签发本地 JWT.
兼容飞书 / GitHub / GitLab / Keycloak / Authing 等任意标准 OIDC 提供方,
通过 .env 配置 (见 backend/.env.example 的 SSO_* 段).
"""
import secrets

import httpx

from app.core.config import settings
from app.core.exceptions import AuthError
from app.security.auth import CurrentUser, create_token

_ROLE_SET = ("viewer", "analyst", "admin")


def _is_localhost(url: str) -> bool:
    """判断 URL 是否指向本机 (用于绕过本机代理)."""
    host = httpx.URL(url).host
    return host in ("localhost", "127.0.0.1", "::1")


class SSOProvider:
    """持有 SSO 配置与一次性 state (防 CSRF 回跳)."""

    def __init__(self) -> None:
        self._states: set[str] = set()
        self.enabled = bool(
            settings.sso_enabled
            and settings.sso_client_id
            and settings.sso_authorize_url
            and settings.sso_token_url
            and settings.sso_userinfo_url
        )
        self.config: dict = {
            "provider_name": settings.sso_provider_name,
            "client_id": settings.sso_client_id,
            "client_secret": settings.sso_client_secret,
            "authorize_url": settings.sso_authorize_url,
            "token_url": settings.sso_token_url,
            "userinfo_url": settings.sso_userinfo_url,
            "scope": settings.sso_scope,
            "role_claim": settings.sso_role_claim,
            "default_role": settings.sso_default_role,
            "redirect_uri": settings.sso_redirect_uri,
        }

    def build_authorize_url(self) -> str:
        """生成带一次性 state 的授权跳转 URL."""
        state = secrets.token_urlsafe(16)
        self._states.add(state)
        cfg = self.config
        return (
            f"{cfg['authorize_url']}?response_type=code"
            f"&client_id={cfg['client_id']}"
            f"&redirect_uri={cfg['redirect_uri']}"
            f"&scope={cfg['scope'].replace(' ', '%20')}"
            f"&state={state}"
        )

    def validate_state(self, state: str) -> bool:
        """校验并消费一次性 state."""
        ok = state in self._states
        self._states.discard(state)
        return ok

    async def exchange_code(self, code: str, client: httpx.AsyncClient | None = None) -> CurrentUser:
        """OAuth2 授权码 -> token -> userinfo -> 映射为本地用户.

        client 参数仅用于测试注入 (httpx.MockTransport); 生产默认自建连接.
        """
        cfg = self.config
        owns_client = client is None
        if client is None:
            # 本机代理 (如 Clash) 会对 localhost 返回 502: 内网目标绕过代理, 外部 IdP 保留代理
            local = _is_localhost(cfg["token_url"]) and _is_localhost(cfg["userinfo_url"])
            client = httpx.AsyncClient(timeout=15, trust_env=not local)
        try:
            tok_resp = await client.post(
                cfg["token_url"],
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": cfg["redirect_uri"],
                    "client_id": cfg["client_id"],
                    "client_secret": cfg["client_secret"],
                },
            )
            if tok_resp.status_code != 200:
                raise AuthError(f"SSO 换码失败: HTTP {tok_resp.status_code}")
            access_token = tok_resp.json().get("access_token")
            if not access_token:
                raise AuthError("SSO 响应缺少 access_token")

            info_resp = await client.get(
                cfg["userinfo_url"],
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if info_resp.status_code != 200:
                raise AuthError(f"SSO 用户信息获取失败: HTTP {info_resp.status_code}")
            claims = info_resp.json()
        finally:
            if owns_client:
                await client.aclose()

        username = (
            claims.get("preferred_username")
            or claims.get("name")
            or claims.get("email", "").split("@")[0]
            or claims.get("sub")
        )
        if not username:
            raise AuthError("SSO userinfo 缺少用户标识")
        role = claims.get(cfg["role_claim"]) or cfg["default_role"]
        if role not in _ROLE_SET:
            role = cfg["default_role"]
        return CurrentUser(username=str(username), role=role)


SSO_PROVIDER = SSOProvider()


def issue_token(user: CurrentUser) -> str:
    """SSO 用户签发本地 JWT (与内置账号同一套密钥/算法)."""
    return create_token(user)
