# -*- coding: utf-8 -*-
"""Semantic Scholar 适配器（Graph API，免费、稳定；可选 API Key 提升限流额度）。"""
from __future__ import annotations

import os
import time

from .base import SearchHit, SearchSourceError, SourceAdapter

API_KEY = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")


class SemanticScholarSource(SourceAdapter):
    id = "semantic_scholar"
    name = "Semantic Scholar"
    langs = ("en",)

    FIELDS = "title,abstract,authors,year,venue,externalIds,url,openAccessPdf,citationCount,publicationTypes"
    API = "https://api.semanticscholar.org/graph/v1/paper/search"

    def search(self, query, year_from, year_to, limit):
        params = {
            "query": query,
            "fields": self.FIELDS,
            "limit": min(limit, 100),
        }
        if year_from or year_to:
            params["year"] = f"{year_from or ''}-{year_to or ''}"
        headers = {"x-api-key": API_KEY} if API_KEY else None
        resp = self._get(self.API, params=params, headers=headers)
        data = resp.json()
        hits: list[SearchHit] = []
        for item in data.get("data") or []:
            if not item.get("title"):
                continue
            ext = item.get("externalIds") or {}
            oa = item.get("openAccessPdf") or {}
            hits.append(
                SearchHit(
                    title=item["title"].strip(),
                    abstract=(item.get("abstract") or "").strip(),
                    authors=[(a.get("name") or "") for a in item.get("authors") or []],
                    year=item.get("year"),
                    venue=(item.get("venue") or "").strip(),
                    doi=ext.get("DOI", ""),
                    arxiv_id=ext.get("ArXiv", ""),
                    url=item.get("url", ""),
                    pdf_url=oa.get("url", ""),
                    citations=item.get("citationCount"),
                    is_open_access=bool(oa.get("url")),
                    extra={"s2_id": item.get("paperId", "")},
                )
            )
        time.sleep(1.1)  # 公共接口礼貌限速
        return hits
