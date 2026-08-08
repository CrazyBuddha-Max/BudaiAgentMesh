"""全局配置, 通过环境变量 / .env 覆盖."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 服务
    app_name: str = "BudaiAgentMesh"
    app_version: str = "0.1.0"
    debug: bool = False
    api_prefix: str = "/api"

    # 元数据库 (PostgreSQL): 显式配置后生效, 否则回退本地 SQLite
    database_url: str = ""
    # 本地默认 SQLite
    sqlite_url: str = "sqlite+aiosqlite:///./data/budai_mesh.db"
    db_echo: bool = False

    # 认证
    jwt_secret: str = "budai-mesh-change-me-in-production-2025-01"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480
    # 内置账号: 用户名:密码:角色, 生产环境应替换为 IdP
    builtin_users: str = "admin:admin123:admin,analyst:analyst123:analyst,viewer:viewer123:viewer"

    # 密钥加密 (Fernet), 用于加密连接器口令
    secret_key: str = "change-me-secret-key"

    # 允许的来源 (CORS)
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # M6: 向量后端选择 (auto/brute_force/pgvector/milvus)
    # auto: PostgreSQL 方言自动用 pgvector, 其余 (SQLite) 用全量余弦兜底
    vector_backend: str = "auto"
    # M6: Milvus 连接地址, 例如 http://localhost:19530 或本地文件 ./data/budai_milvus.db
    milvus_uri: str = ""

    # M6: 观测遥测 (OTLP/HTTP), 配置端点后启用 (如 http://localhost:4318)
    otel_endpoint: str = ""
    otel_service_name: str = "budai-agent-mesh"

    # M6: SSO / OAuth2.0 授权码登录 (兼容任意标准 OIDC 提供方)
    sso_enabled: bool = False
    sso_provider_name: str = "SSO"
    sso_client_id: str = ""
    sso_client_secret: str = ""
    sso_authorize_url: str = ""
    sso_token_url: str = ""
    sso_userinfo_url: str = ""
    sso_scope: str = "openid profile email"
    sso_role_claim: str = "role"  # userinfo 中承载角色的字段名
    sso_default_role: str = "viewer"
    sso_redirect_uri: str = "http://localhost:5173/login"  # 前端回调页 (须与 IdP 白名单一致)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
