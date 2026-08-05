"""向量化服务: 可插拔 Embedding 提供方.

- HashEmbedder: 零依赖离线实现 (字符 3-gram 特征哈希 + L2 归一化), 演示开箱即用
- OpenAIEmbedder: 配置 OPENAI_API_KEY 后启用, 检索质量更高
- HuggingFaceEmbedder: 本地模型 (可选)

生产建议 M3 统一走 Embedding 网关 (多模型路由 + 成本计量).
"""
import hashlib
import math
import os
from abc import ABC, abstractmethod

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


def get_embedder() -> Embedder:
    """按环境选择 Embedding 提供方: OpenAI -> 本地哈希兜底."""
    if os.getenv("OPENAI_API_KEY"):
        try:
            return OpenAIEmbedder()
        except BizError:
            pass  # openai 依赖缺失时静默降级
    return HashEmbedder()
