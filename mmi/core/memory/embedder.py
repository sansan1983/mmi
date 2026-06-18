"""mmi.core.memory.embedder —— 嵌入器协议 + 实现 + 单例管理。

依赖项:schema (DEFAULT_EMBEDDING_MODEL)。
被依赖:store, search。
"""

from __future__ import annotations

import hashlib
import threading
from typing import Protocol

from mmi.core.memory.schema import DEFAULT_EMBEDDING_MODEL


class Embedder(Protocol):
    """嵌入器协议。实现需返回固定维度、与文本相关的稠密向量。"""

    @property
    def dim(self) -> int: ...

    def embed(self, text: str) -> list[float]: ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbedder:
    """确定性假嵌入器（用于测试 / 无 sentence-transformers 时降级）。

    把文本 sha256 后切成 64 维 float 区间 [-1, 1] —— 维度固定、内容相关、
    完全可复现。无外部依赖、无模型下载。
    """

    DIM = 64

    @property
    def dim(self) -> int:
        return self.DIM

    def embed(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode("utf-8")).digest()
        # 64 维需要 64 字节，sha256 给 32 字节 → 重复拼接
        raw = h + h
        return [(b - 128) / 128.0 for b in raw[: self.DIM]]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class SentenceTransformerEmbedder:
    """sentence-transformers 嵌入器（生产用）。"""

    def __init__(self, model_name: str = DEFAULT_EMBEDDING_MODEL) -> None:
        # 延迟导入：用户没装 sentence-transformers 时不阻塞核心
        from sentence_transformers import SentenceTransformer  # noqa: WPS433

        self._model = SentenceTransformer(model_name)
        self._dim = self._model.get_sentence_embedding_dimension()

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        v = self._model.encode(text, normalize_embeddings=True)
        return v.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        vs = self._model.encode(texts, normalize_embeddings=True)
        return [v.tolist() for v in vs]


_embedder: Embedder | None = None
_embedder_lock = threading.Lock()


def get_embedder() -> Embedder:
    """获取当前 embedder。优先用显式注入的，否则懒加载 sentence-transformers，
    失败时降级到 HashEmbedder。
    """
    global _embedder
    if _embedder is not None:
        return _embedder
    with _embedder_lock:
        if _embedder is not None:
            return _embedder
        try:
            _embedder = SentenceTransformerEmbedder(DEFAULT_EMBEDDING_MODEL)
        except Exception:
            # 任何异常（缺包 / 无网络 / 模型不可用）→ 降级
            _embedder = HashEmbedder()
        return _embedder


def set_embedder(embedder: Embedder | None) -> None:
    """注入/重置 embedder。传 None 重置为懒加载默认。"""
    global _embedder
    with _embedder_lock:
        _embedder = embedder
