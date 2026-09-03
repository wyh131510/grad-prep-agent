# -*- coding: utf-8 -*-
"""万方数据适配器：HTML 页面尽力抓取。"""
from __future__ import annotations

import re

from .base import SearchHit, SourceAdapter
from ..utils import make_soup, parse_year


class WanfangSource(SourceAdapter):
    id = "wanfang"
    name = "万方数据"
    langs = ("zh",)

    API = "https://s.wanfangdata.com.cn/paper"

    def search(self, query, year_from, year_to, limit):
        resp = self._get(self.API, params={"q": query}, headers={"Referer": "https://www.wanfangdata.com.cn/"})
        soup = make_soup(resp.text)
        hits: list[SearchHit] = []
        for item in soup.select(".normal-list, .item-list li, .list-item")[: limit]:
            a = item.select_one("a[href*='detail']") or item.select_one("a")
            if not a or not a.get_text(strip=True):
                continue
            title = a.get_text(" ", strip=True)
            info = item.get_text(" ", strip=True)
            authors: list[str] = []
            m = re.search(r"作者[:：]?\s*([^\d]+?)(?=\s+\d{4}|$)", info)
            if m:
                authors = [x.strip() for x in re.split(r"[;,，]", m.group(1)) if x.strip()]
            year = parse_year(info)
            if year and year_from and year < year_from:
                continue
            if year and year_to and year > year_to:
                continue
            hits.append(
                SearchHit(
                    title=title,
                    authors=authors,
                    year=year,
                    url=a.get("href", ""),
                    extra={"raw_info": info[:300]},
                )
            )
        return hits
