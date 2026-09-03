# -*- coding: utf-8 -*-
"""解析结果统一结构（HTML / PDF / 图片最终都收敛到 ParsedPage）。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FigureInfo:
    caption: str = ""
    description: str = ""  # 真实来自文献（图注原文），不由 AI 生成
    page: int | None = None
    image: str = ""  # 相对 download_dir 的图片路径


@dataclass
class ParsedPage:
    """统一解析结构。"""

    title: str = ""
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    year: int | None = None
    venue: str = ""
    doi: str = ""
    keywords: list[str] = field(default_factory=list)
    pdf_url: str = ""
    url: str = ""
    text: str = ""  # 正文全文（供检索与片段提取）
    snippets: list[dict] = field(default_factory=list)  # {text, section, page}
    figures: list[FigureInfo] = field(default_factory=list)
    tables: list[dict] = field(default_factory=list)  # {text, page}
    note: str = ""  # 解析说明（如“已启用 OCR”“图片型 PDF 仅提取前 4 页”）
