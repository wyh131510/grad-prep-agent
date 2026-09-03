# -*- coding: utf-8 -*-
"""Reranker 精排（第三重）：本地 bge-reranker，可选依赖，未安装时由引擎降级为 LLM 精排。"""
from __future__ import annotations

import os
import threading

from ..config import DATA_DIR

MODEL_NAME = os.environ.get("GRAD_PREP_RERANK_MODEL", "BAAI/bge-reranker-base")

# 国内网络默认走 hf-mirror 镜像下载模型；如需官方源，设置环境变量 HF_ENDPOINT=https://huggingface.co
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")


class Reranker:
    _instance: "Reranker | None" = None
    _lock = threading.Lock()

    def __init__(self):
        self._model = None
        self.error = ""
        self._tried = False

    @classmethod
    def get(cls) -> "Reranker":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _ensure(self) -> bool:
        if self._tried:
            return self._model is not None
        self._tried = True
        try:
            from sentence_transformers import CrossEncoder

            cache = DATA_DIR / "models"
            cache.mkdir(parents=True, exist_ok=True)
            os.environ.setdefault("TRANSFORMERS_CACHE", str(cache))
            self._model = CrossEncoder(MODEL_NAME)
        except Exception as exc:  # noqa: BLE001
            self.error = f"本地 reranker 不可用（{exc}），将降级为 LLM 精排或跳过精排。"
            self._model = None
        return self._model is not None

    @property
    def available(self) -> bool:
        return self._ensure()

    def scores(self, query: str, docs: list[str]) -> list[float] | None:
        """返回各 doc 与 query 的相关分（0~1）；不可用返回 None。"""
        if not self._ensure() or not docs:
            return None
        pairs = [(query, d) for d in docs]
        preds = self._model.predict(pairs, show_progress_bar=False, batch_size=16)
        if len(preds.shape) == 1:
            preds = preds.reshape(-1, 1)
        return [max(0.0, min(1.0, float(p[0]))) for p in preds]


reranker = Reranker.get()
