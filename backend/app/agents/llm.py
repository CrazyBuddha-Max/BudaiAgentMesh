"""大模型接入服务 (M7): LLM 提供方管理 + 统一 OpenAI 兼容调用.

- 支持任意 OpenAI 兼容协议提供方: OpenAI / DeepSeek / 通义千问 / Ollama 等
- api_key 以 Fernet 加密存储, 绝不回显
- chat_completion / embed / test_connection 统一走 httpx (零新增依赖)
- 本机地址 (Ollama 等) 绕过系统代理; 外网提供方保留代理
"""
import datetime as dt
from typing import Any

import httpx
from sqlalchemy import String, Text, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.access.crypto import decrypt_secret, encrypt_secret
from app.core.database import Base
from app.core.exceptions import BizError, NotFoundError

PROVIDER_TYPES = ("openai", "deepseek", "qwen", "ollama", "custom")


class LLMProvider(Base):
    """大模型提供方: 一份配置即可被多个 Agent / 向量化复用."""

    __tablename__ = "llm_providers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    provider_type: Mapped[str] = mapped_column(String(32), default="openai")
    api_base: Mapped[str] = mapped_column(String(512))  # 如 https://api.openai.com/v1 或 http://localhost:11434/v1
    api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str] = mapped_column(String(128))  # 对话模型, 如 gpt-4o-mini / deepseek-chat / qwen-plus
    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)  # 向量化模型 (可空)
    temperature: Mapped[float] = mapped_column(default=0.2)
    max_tokens: Mapped[int] = mapped_column(default=2048)
    enabled: Mapped[bool] = mapped_column(default=True)
    is_default: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())


def _is_localhost(url: str) -> bool:
    try:
        host = httpx.URL(url).host
        return host in ("localhost", "127.0.0.1", "::1")
    except Exception:
        return False


def _headers(provider: LLMProvider) -> dict:
    headers = {"Content-Type": "application/json"}
    api_key = decrypt_secret(provider.api_key_enc) if provider.api_key_enc else None
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _chat_url(provider: LLMProvider) -> str:
    return f"{provider.api_base.rstrip('/')}/chat/completions"


def _embed_url(provider: LLMProvider) -> str:
    return f"{provider.api_base.rstrip('/')}/embeddings"


# ---------- CRUD ----------


async def list_providers(session: AsyncSession) -> list[LLMProvider]:
    result = await session.execute(select(LLMProvider).order_by(LLMProvider.is_default.desc(), LLMProvider.name))
    return list(result.scalars().all())


async def get_provider(session: AsyncSession, provider_id: int) -> LLMProvider:
    provider = await session.get(LLMProvider, provider_id)
    if provider is None:
        raise NotFoundError(f"模型提供方不存在: {provider_id}")
    return provider


async def get_default_provider(session: AsyncSession) -> LLMProvider | None:
    provider = (
        await session.execute(select(LLMProvider).where(LLMProvider.is_default.is_(True)))
    ).scalar_one_or_none()
    return provider


async def create_provider(
    session: AsyncSession,
    name: str,
    provider_type: str,
    api_base: str,
    api_key: str | None,
    model: str,
    embedding_model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    is_default: bool = False,
) -> LLMProvider:
    if not name or not api_base or not model:
        raise BizError("名称/API 地址/模型不能为空")
    if provider_type not in PROVIDER_TYPES:
        raise BizError(f"不支持的提供方类型: {provider_type} (支持 {'/'.join(PROVIDER_TYPES)})")
    existing = (await session.execute(select(LLMProvider).where(LLMProvider.name == name))).scalar_one_or_none()
    if existing is not None:
        raise BizError(f"提供方已存在: {name}")

    if is_default:
        await _clear_default(session)
    provider = LLMProvider(
        name=name,
        provider_type=provider_type,
        api_base=api_base,
        api_key_enc=encrypt_secret(api_key) if api_key else None,
        model=model,
        embedding_model=embedding_model,
        temperature=temperature,
        max_tokens=max_tokens,
        is_default=is_default,
    )
    session.add(provider)
    await session.commit()
    await session.refresh(provider)
    return provider


async def update_provider(
    session: AsyncSession,
    provider_id: int,
    payload: dict,
) -> LLMProvider:
    provider = await get_provider(session, provider_id)
    data = dict(payload)
    if "api_key" in data:
        key = data.pop("api_key")
        provider.api_key_enc = encrypt_secret(key) if key else None
    for field in ("name", "provider_type", "api_base", "model", "embedding_model", "temperature", "max_tokens", "enabled"):
        if field in data and data[field] is not None:
            setattr(provider, field, data[field])
    if data.get("is_default"):
        await _clear_default(session)
        provider.is_default = True
    await session.commit()
    await session.refresh(provider)
    return provider


async def delete_provider(session: AsyncSession, provider_id: int) -> None:
    provider = await get_provider(session, provider_id)
    await session.delete(provider)
    await session.commit()


async def set_default_provider(session: AsyncSession, provider_id: int) -> LLMProvider:
    provider = await get_provider(session, provider_id)
    await _clear_default(session)
    provider.is_default = True
    await session.commit()
    await session.refresh(provider)
    return provider


async def _clear_default(session: AsyncSession) -> None:
    from sqlalchemy import update

    await session.execute(update(LLMProvider).values(is_default=False).where(LLMProvider.is_default.is_(True)))


# ---------- 统一调用 (OpenAI 兼容协议) ----------


async def chat_completion(
    provider: LLMProvider,
    messages: list[dict],
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """对话补全: 返回 assistant 文本 (真实调用, 失败抛 BizError)."""
    if not provider.enabled:
        raise BizError(f"模型提供方已停用: {provider.name}")
    payload: dict[str, Any] = {
        "model": provider.model,
        "messages": messages,
        "temperature": temperature if temperature is not None else provider.temperature,
    }
    if max_tokens or provider.max_tokens:
        payload["max_tokens"] = max_tokens or provider.max_tokens
    local = _is_localhost(provider.api_base)
    try:
        async with httpx.AsyncClient(timeout=120, trust_env=not local) as client:
            resp = await client.post(_chat_url(provider), json=payload, headers=_headers(provider))
        if resp.status_code != 200:
            raise BizError(f"LLM 调用失败: HTTP {resp.status_code} {resp.text[:300]}")
        data = resp.json()
        return str(data["choices"][0]["message"]["content"]).strip()
    except httpx.HTTPError as exc:
        raise BizError(f"LLM 不可达: {exc.__class__.__name__} ({provider.api_base})") from exc


async def embed_texts(provider: LLMProvider, texts: list[str]) -> list[list[float]]:
    """真实向量化: 调用提供方 /embeddings (OpenAI 兼容协议)."""
    model = provider.embedding_model or provider.model
    local = _is_localhost(provider.api_base)
    try:
        async with httpx.AsyncClient(timeout=120, trust_env=not local) as client:
            resp = await client.post(
                _embed_url(provider),
                json={"model": model, "input": texts},
                headers=_headers(provider),
            )
        if resp.status_code != 200:
            raise BizError(f"向量化失败: HTTP {resp.status_code} {resp.text[:300]}")
        data = resp.json()
        return [list(item["embedding"]) for item in data["data"]]
    except httpx.HTTPError as exc:
        raise BizError(f"向量化服务不可达: {exc.__class__.__name__} ({provider.api_base})") from exc


async def test_connection(provider: LLMProvider) -> str:
    """最小连通性验证: 发送一个 1-token 对话请求."""
    reply = await chat_completion(
        provider,
        [{"role": "user", "content": "ping, 只回复 pong"}],
        temperature=0,
        max_tokens=8,
    )
    return f"连接成功, 模型响应: {reply[:40]}" if reply else "连接成功"
