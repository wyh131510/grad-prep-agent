# -*- coding: utf-8 -*-
"""arXiv 适配器（Atom API，免费、稳定）。"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from .base import SearchHit, SearchSourceError, SourceAdapter
from ..utils import parse_year

NS = {"a": "http://www.w3.org/2005/Atom"}


class ArxivSource(SourceAdapter):
    id = "arxiv"
    name = "arXiv"
    langs = ("en",)

    API = "http://export.arxiv.org/api/query"

    def search(self, query, year_from, year_to, limit):
        # 去除对 arXiv 检索有干扰的字符
        q = re.sub(r'["&|()]', " ", query).strip()
        params = {
            "search_query": f'all:"{q}"',
            "start": 0,
            "max_results": min(limit, 30),
            "sortBy": "relevance",
        }
        resp = self._get(self.API, params=params)
        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError as exc:
            raise SearchSourceError(f"arXiv 返回内容解析失败：{exc}") from exc

        hits: list[SearchHit] = []
        for entry in root.findall("a:entry", NS):
            title = " ".join((entry.findtext("a:title", "", NS) or "").split())
            summary = " ".join((entry.findtext("a:summary", "", NS) or "").split())
            arxiv_id = (entry.findtext("a:id", "", NS) or "").rsplit("/abs/", 1)[-1]
            year = parse_year(entry.findtext("a:published", "", NS) or "")
            if year and year_from and year < year_from:
                continue
            if year and year_to and year > year_to:
                continue
            authors = [
                " ".join((n.findtext("a:name", "", NS) or "").split())
                for n in entry.findall("a:author", NS)
            ]
            doi = ""
            for link in entry.findall("a:link", NS):
                href = link.get("href", "")
                if "doi.org" in href:
                    doi = href.rsplit("doi.org/", 1)[-1]
            hits.append(
                SearchHit(
                    title=title,
                    abstract=summary,
                    authors=authors,
                    year=year,
                    venue="arXiv",
                    arxiv_id=arxiv_id,
                    url=f"https://arxiv.org/abs/{arxiv_id}",
                    pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
                    doi=doi,
                )
            )
        return hits
