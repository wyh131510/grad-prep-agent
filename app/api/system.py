# -*- coding: utf-8 -*-
"""系统接口：健康检查与概览统计。"""
from __future__ import annotations

from fastapi import APIRouter

from .. import __version__
from ..store import repo

router = APIRouter(tags=["system"])


def _installed(module: str) -> bool:
    """仅检查包是否安装（find_spec 不触发 import，避免 torch 等包的 DLL 加载副作用）。"""
    import importlib.util

    return importlib.util.find_spec(module) is not None


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "optional": {
            "embedding": _installed("sentence_transformers"),  # BGE 向量检索
            "ocr": _installed("rapidocr_onnxruntime"),  # 图片/扫描件 OCR
        },
    }


@router.get("/stats")
def stats() -> dict:
    return repo.stats()
