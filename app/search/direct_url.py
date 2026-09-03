# -*- coding: utf-8 -*-
"""直链抓取适配器：用户提供 URL 列表（HTML 页面或 PDF），逐条下载并走统一解析管线。"""
from __future__ import annotations

import re

from .base import SearchHit, SearchSourceError, SourceAdapter


class DirectUrlSource(SourceAdapter):
    id = "direct_url"
    name = "自定义 URL"
    langs = ()

    def __init__(self, timeout: int = 30, urls: list[str] | None = None):
        super().__init__(timeout)
        self.urls = [u.strip() for u in (urls or []) if u.strip()]

    def search(self, query="", year_from=None, year_to=None, limit=10):
        # 本适配器不做“搜索”，而是按给定 URL 抓取整篇文档，由引擎统一解析
        return []

    def fetch_documents(self, urls: list[str] | None = None):
        """逐个抓取 URL 内容，返回 (url, content_type, bytes)。"""
        for url in (urls or self.urls)[:20]:
            try:
                resp = self._get(url)
            except SearchSourceError:
                continue
            ctype = resp.headers.get("content-type", "")
            yield url, ctype, resp.content


def looks_like_pdf(url: str, content_type: str = "") -> bool:
    if content_type and "pdf" in content_type.lower():
        return True
    return bool(re.search(r"\.pdf($|\?)", url, re.I))
