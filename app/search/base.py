# -*- coding: utf-8 -*-
"""文献来源适配器基类：所有来源统一收敛到 SearchHit 结构。"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx


class SearchSourceError(RuntimeError):
    """来源抓取失败（网络 / 反爬 / 无结果），引擎捕获后记录并继续其他来源。"""


@dataclass
class SearchHit:
    """来源适配器返回的原始命中（统一结构，入库前还需过解析/清洗）。"""

    title: str
    url: str = ""
    pdf_url: str = ""
    abstract: str = ""
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str = ""
    doi: str = ""
    arxiv_id: str = ""
    keywords: list[str] = field(default_factory=list)
    citations: int | None = None
    is_open_access: bool = False
    extra: dict = field(default_factory=dict)


UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 grad-prep-agent/0.1"
)


class SourceAdapter(ABC):
    """来源适配器：新增来源只需继承并实现 search()，不改动下游。"""

    id: str = ""
    name: str = ""
    langs: tuple[str, ...] = ("en", "zh")  # 支持哪些语言的查询词

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    def _get(self, url: str, **kw) -> httpx.Response:
        last_429 = ""
        headers = {"User-Agent": UA}
        if "headers" in kw and kw["headers"]:
            headers.update(kw.pop("headers"))
        for attempt in range(4):  # 429 限流自动退避重试
            try:
                with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=headers) as client:
                    resp = client.get(url, **kw)
            except httpx.HTTPError as exc:
                raise SearchSourceError(f"{self.name} 网络请求失败：{exc}") from exc
            if resp.status_code == 429:
                last_429 = f"{self.name} 触发限流（429）"
                time.sleep(2.0 * (attempt + 1))
                continue
            if resp.status_code >= 400:
                raise SearchSourceError(f"{self.name} 返回 HTTP {resp.status_code}")
            return resp
        raise SearchSourceError(f"{last_429}，请稍后重试")

    @abstractmethod
    def search(self, query: str, year_from: int | None, year_to: int | None, limit: int) -> list[SearchHit]:
        """执行一次检索，返回命中列表（可能为空）。失败时抛 SearchSourceError。"""

    def __repr__(self) -> str:
        return f"<Source {self.id}>"
