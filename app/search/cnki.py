# -*- coding: utf-8 -*-
"""知网（CNKI）适配器：尽力抓取。知网反爬严格，失败会给出替代方案。"""
from __future__ import annotations

import re

from .base import SearchHit, SearchSourceError, SourceAdapter
from ..utils import parse_year


class CnkiSource(SourceAdapter):
    id = "cnki"
    name = "知网 CNKI"
    langs = ("zh",)

    API = "https://kns.cnki.net/kns8s/brief/grid"

    def search(self, query, year_from, year_to, limit):
        # 知网检索接口需完整参数与校验头，任何异常都转为可读错误
        try:
            resp = self._get(
                self.API,
                params={
                    "platform": "kns",
                    "searchType": "1",
                    "keyword": query,
                    "pageIndex": 1,
                    "pageSize": min(limit, 20),
                    "sortType": "REL",
                },
                headers={
                    "Referer": "https://kns.cnki.net/kns8s/defaultresult/index",
                    "Accept": "application/json, text/plain, */*",
                },
            )
            data = resp.json()
        except SearchSourceError as exc:
            raise SearchSourceError(
                f"{exc}。知网反爬限制严格，建议改用「文献导入」功能（在知网导出 EndNote 格式后上传）"
            ) from exc
        except ValueError as exc:
            raise SearchSourceError(
                f"知网返回的不是 JSON（可能被反爬拦截）。建议改用「文献导入」功能（知网导出 EndNote 格式后上传）"
            ) from exc

        hits: list[SearchHit] = []
        # 知网 grid 接口常见结构：data.records.data 列表
        records = data.get("data", {}) if isinstance(data, dict) else {}
        rows = records.get("records", {}).get("data", []) if isinstance(records, dict) else []
        if not rows and isinstance(records, list):
            rows = records
        for row in rows:
            if not isinstance(row, dict):
                continue
            title = re.sub(r"<[^>]+>", "", str(row.get("TitleCN", row.get("title", "")))).strip()
            if not title:
                continue
            authors = str(row.get("AuthorCN", row.get("authors", "")))
            authors = [a.strip() for a in re.split(r"[;,;]", authors) if a.strip()]
            year = parse_year(row.get("Year", row.get("publishdate", "")))
            abstract = re.sub(r"<[^>]+>", "", str(row.get("AbstractCN", row.get("abstract", "")))).strip()
            src_name = re.sub(r"<[^>]+>", "", str(row.get("SourceName", row.get("sourcename", "")))).strip()
            if year and year_from and year < year_from:
                continue
            if year and year_to and year > year_to:
                continue
            hits.append(
                SearchHit(
                    title=title,
                    abstract=abstract,
                    authors=authors,
                    year=year,
                    venue=src_name,
                    url=f"https://kns.cnki.net/kcms2/article/abstract?v={row.get('DbCode', '')}",
                    keywords=[],
                    extra={"cnki_db": row.get("DbCode", "")},
                )
            )
        return hits
