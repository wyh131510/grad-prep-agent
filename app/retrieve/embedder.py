# -*- coding: utf-8 -*-
"""向量语义匹配（第二重）：本地 BGE 模型，可选依赖，未安装时自动降级。"""
from __future__ import annotations

import os
import threading

from ..config import DATA_DIR

MODEL_NAME = os.environ.get("GRAD_PREP_EMBED_MODEL", "BAAI/bge-small-zh-v1.5")

# 国内网络默认走 hf-mirror 镜像下载模型；如需官方源，设置环境变量 HF_ENDPOINT=https://huggingface.co
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")


class Embedder:
    _instance: "Embedder | None" = None
    _lock = threading.Lock()

    def __init__(self):
        self._model = None
        self.error = ""
        self._tried = False

    @classmethod
    def get(cls) -> "Embedder":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _ensure(self) -> bool:
        if self._tried:
            return self._model is not None
        self._tried = True
        try:
            from sentence_transformers import SentenceTransformer

            cache = DATA_DIR / "models"
            cache.mkdir(parents=True, exist_ok=True)
            os.environ.setdefault("TRANSFORMERS_CACHE", str(cache))
            self._model = SentenceTransformer(MODEL_NAME)
            self._model.encode("预热", normalize_embeddings=True)  # 触发实际加载
        except Exception as exc:  # noqa: BLE001
            self.error = (
                f"本地向量模型不可用（{exc}）。"
                "可安装 sentence-transformers 与 torch，或将 HF_ENDPOINT 设为 https://hf-mirror.com 后重试；"
                "当前将退化为 BM25 + LLM 精排。"
            )
            self._model = None
        return self._model is not None

    @property
    def available(self) -> bool:
        return self._ensure()

    def encode(self, texts: list[str]):
        """返回归一化向量矩阵 (n, dim)；不可用时返回 None。"""
        if not self._ensure() or not texts:
            return None
        import numpy as np

        vecs = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False, batch_size=16)
        return np.asarray(vecs, dtype="float32")


embedder = Embedder.get()
