# -*- coding: utf-8 -*-
"""OpenAlex 适配器：免费、稳定、无需 API Key，收录中英文文献（含知网/万方等中文期刊元数据），
提供开放获取 PDF 直链，可替代被反爬限制的知网/万方。"""
from __future__ import annotations

from .base import SearchHit, SourceAdapter
from ..utils import parse_year


def _deinvert(inv: dict | None) -> str:
    """OpenAlex 摘要为倒排索引，还原为正文文本。"""
    if not inv:
        return ""
    pos: dict[int, str] = {}
    for word, positions in inv.items():
        for p in positions:
            pos[p] = word
    return " ".join(pos[i] for i in sorted(pos))


class OpenAlexSource(SourceAdapter):
    id = "openalex"
    name = "OpenAlex"
    langs = ("en", "zh")

    API = "https://api.openalex.org/works"

    def search(self, query, year_from, year_to, limit):
        params = {
            "search": query,
            "per-page": min(limit, 25),
            "sort": "relevance_score:desc",
            "mailto": "grad-prep-agent@example.com",
        }
        filters = []
        if year_from:
            filters.append(f"from_publication_date:{year_from}-01-01")
        if year_to:
            filters.append(f"to_publication_date:{year_to}-12-31")
        if filters:
            params["filter"] = ",".join(filters)
        resp = self._get(self.API, params=params)
        data = resp.json()
        hits: list[SearchHit] = []
        for w in data.get("results") or []:
            title = (w.get("title") or w.get("display_name") or "").strip()
            if not title:
                continue
            authors = [
                (a.get("author") or {}).get("display_name", "")
                for a in w.get("authorships") or []
            ]
            authors = [a for a in authors if a]
            year = parse_year(w.get("publication_year"))
            loc = w.get("primary_location") or {}
            src = loc.get("source") or {}
            venue = src.get("display_name") or ""
            landing = loc.get("landing_page_url") or ""
            doi = (w.get("doi") or "").replace("https://doi.org/", "")
            oa = w.get("open_access") or {}
            pdf_url = oa.get("oa_url", "") if oa.get("is_oa") else ""
            keywords = [c.get("display_name", "") for c in (w.get("concepts") or [])[:5]]
            hits.append(
                SearchHit(
                    title=title,
                    abstract=_deinvert(w.get("abstract_inverted_index"))[:6000],
                    authors=authors,
                    year=year,
                    venue=venue,
                    doi=doi,
                    url=landing or (f"https://doi.org/{doi}" if doi else w.get("id", "")),
                    pdf_url=pdf_url,
                    citations=w.get("cited_by_count"),
                    is_open_access=bool(pdf_url),
                    keywords=[k for k in keywords if k],
                    extra={"openalex_id": w.get("id", "")},
                )
            )
        return hits
