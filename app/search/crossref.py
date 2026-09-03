# -*- coding: utf-8 -*-
"""CrossRef 适配器（DOI 元数据，免费、稳定，覆盖期刊/会议）。"""
from __future__ import annotations

from .base import SearchHit, SourceAdapter
from ..utils import parse_year


class CrossrefSource(SourceAdapter):
    id = "crossref"
    name = "CrossRef"
    langs = ("en",)

    API = "https://api.crossref.org/works"

    def search(self, query, year_from, year_to, limit):
        params = {
            "query": query,
            "rows": min(limit, 20),
            "select": "DOI,title,abstract,author,container-title,issued,URL,is-referenced-by-count,subject,type",
            "mailto": "grad-prep-agent@example.com",  # 礼貌池
        }
        if year_from or year_to:
            filters = []
            if year_from:
                filters.append(f"from-pub-date:{year_from}-01-01")
            if year_to:
                filters.append(f"until-pub-date:{year_to}-12-31")
            params["filter"] = ",".join(filters)
        resp = self._get(self.API, params=params)
        data = resp.json()
        hits: list[SearchHit] = []
        for item in (data.get("message") or {}).get("items") or []:
            title = (item.get("title") or [""])[0]
            if not title:
                continue
            year = None
            issued = item.get("issued") or {}
            if issued.get("date-parts"):
                year = parse_year(issued["date-parts"][0][0])
            authors = [
                f"{a.get('given', '')} {a.get('family', '')}".strip()
                for a in item.get("author") or []
            ]
            venue = ((item.get("container-title") or [""])[0]) or ""
            hits.append(
                SearchHit(
                    title=title.strip(),
                    abstract=re_clean(item.get("abstract") or ""),
                    authors=[a for a in authors if a],
                    year=year,
                    venue=venue,
                    doi=item.get("DOI", ""),
                    url=item.get("URL", "") or (f"https://doi.org/{item['DOI']}" if item.get("DOI") else ""),
                    citations=item.get("is-referenced-by-count"),
                )
            )
        return hits


def re_clean(text: str) -> str:
    import re

    text = re.sub(r"<[^>]+>", " ", text or "")
    return " ".join(text.split())
