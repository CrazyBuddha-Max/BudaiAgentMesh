"""向量化服务: 可插拔 Embedding 提供方.

- HashEmbedder: 零依赖离线实现 (字符 3-gram 特征哈希 + L2 归一化), 演示开箱即用
- OpenAIEmbedder: 配置 OPENAI_API_KEY 后启用, 检索质量更高
- ProviderEmbedder: 使用大模型接入面板配置的默认提供方 (M7, OpenAI 兼容 /embeddings), 真实向量化
- HuggingFaceEmbedder: 本地模型 (可选)

生产建议 M3 统一走 Embedding 网关 (多模型路由 + 成本计量).
"""
import hashlib
import math
import os
from abc import ABC, abstractmethod

import httpx

from app.core.exceptions import BizError


class Embedder(ABC):
    """Embedding 契约."""

    dim: int

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """单条文本向量化."""

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class HashEmbedder(Embedder):
    """离线特征哈希: 字符 3-gram -> 定长稀疏向量 (演示/离线兜底).

    确定性 (md5), 跨进程一致; 语义质量有限, 仅用于能力验证.
    """

    dim = 768
    _gram = 3

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        text = text.strip().lower()
        for i in range(max(1, len(text) - self._gram + 1)):
            gram = text[i : i + self._gram]
            digest = int(hashlib.md5(gram.encode("utf-8")).hexdigest(), 16)
            vec[digest % self.dim] += 1.0 if (digest >> 8) % 2 else -1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0:
            return vec
        return [v / norm for v in vec]


class OpenAIEmbedder(Embedder):
    """OpenAI text-embedding-3-small (需 OPENAI_API_KEY, 可选)."""

    dim = 1536

    def __init__(self, model: str = "text-embedding-3-small") -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise BizError("使用 OpenAI 向量化需安装 openai 依赖") from exc
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise BizError("未配置 OPENAI_API_KEY")
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def embed(self, text: str) -> list[float]:
        resp = self._client.embeddings.create(model=self._model, input=[text])
        return list(resp.data[0].embedding)


class ProviderEmbedder(Embedder):
    """真实向量化 (M7): 使用大模型接入面板的默认提供方 (OpenAI 兼容 /embeddings).

    同步实现 (httpx.Client), 适配 Embedder 契约; 未配置提供方/调用失败时抛 BizError,
    由 get_embedder() 捕获后回退 HashEmbedder.
    """

    def __init__(self, provider: object | None = None) -> None:
        """provider 为 LLMProvider 对象或 None (None 时从本地库读取默认)."""
        if provider is None:
            provider = self._load_default()
        if provider is None:
            raise BizError("未配置默认模型提供方, 无法真实向量化")
        self._provider = provider
        self._model = provider.embedding_model or provider.model
        self.dim = 0  # 由首次嵌入推断
        api_key = self._decrypt_key(provider)
        self._headers = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"
        self._url = f"{provider.api_base.rstrip('/')}/embeddings"

    @staticmethod
    def _load_default() -> object | None:
        """从本地 SQLite 直读默认提供方 (演示环境); PG 生产建议用 OPENAI_API_KEY 或预置缓存."""
        try:
            import sqlite3
            import urllib.parse

            from app.core.config import settings

            url = settings.sqlite_url
            db_path = urllib.parse.urlparse(url.replace("sqlite+aiosqlite://", "sqlite://")).path
            if not db_path:
                return None
            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute(
                    "SELECT id, name, api_base, api_key_enc, model, embedding_model FROM llm_providers "
                    "WHERE enabled=1 AND is_default=1 LIMIT 1"
                ).fetchone()
            finally:
                conn.close()
            if not row:
                return None
            from types import SimpleNamespace

            return SimpleNamespace(
                id=row[0], name=row[1], api_base=row[2], api_key_enc=row[3],
                model=row[4], embedding_model=row[5],
            )
        except Exception:
            return None

    @staticmethod
    def _decrypt_key(provider) -> str | None:
        enc = getattr(provider, "api_key_enc", None)
        if not enc:
            return None
        try:
            from app.access.crypto import decrypt_secret

            return decrypt_secret(enc)
        except Exception:
            return None

    def embed(self, text: str) -> list[float]:
        resp = httpx.post(
            self._url,
            json={"model": self._model, "input": [text]},
            headers=self._headers,
            timeout=60,
        )
        if resp.status_code != 200:
            raise BizError(f"真实向量化失败: HTTP {resp.status_code} {resp.text[:200]}")
        vec = resp.json()["data"][0]["embedding"]
        self.dim = len(vec)
        return list(vec)


def get_embedder() -> Embedder:
    """按环境选择 Embedding 提供方: OpenAI -> LLM 面板默认提供方 -> 本地哈希兜底."""
    if os.getenv("OPENAI_API_KEY"):
        try:
            return OpenAIEmbedder()
        except BizError:
            pass  # openai 依赖缺失时静默降级
    try:  # M7: 大模型面板配置了默认提供方且可向量化时, 走真实 embedding
        return ProviderEmbedder()
    except BizError:
        pass
    return HashEmbedder()
