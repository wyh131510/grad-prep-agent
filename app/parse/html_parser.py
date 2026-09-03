# -*- coding: utf-8 -*-
"""HTML 页面解析：元数据优先取学术站点标准 meta 标签，正文用 readability 提取。"""
from __future__ import annotations

import re

from ..utils import clean_text, make_soup, parse_year, strip_html
from .common import ParsedPage

_SENT_SPLIT = re.compile(r"(?<=[.。!！?？;；:：])\s*")


def _meta(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        node = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name})
        if node and node.get("content"):
            return clean_text(node["content"])
    return ""


def _meta_all(soup: BeautifulSoup, *names: str) -> list[str]:
    out: list[str] = []
    for node in soup.find_all("meta"):
        if node.get("name") in names or node.get("property") in names:
            v = clean_text(node.get("content", ""))
            if v and v not in out:
                out.append(v)
    return out


def parse_html(url: str, html: str, keywords: list[str] | None = None) -> ParsedPage:
    keywords = keywords or []
    page = ParsedPage(url=url)
    soup = make_soup(html)

    # ---- 元数据（学术站通用 citation_* / DC / og 标签）
    title = _meta(soup, "citation_title", "dc.title", "DC.title", "og:title")
    if not title and soup.title:
        title = clean_text(soup.title.get_text())
    page.title = title

    page.authors = _meta_all(soup, "citation_author", "dc.creator", "DC.creator")
    abstract = _meta(soup, "citation_abstract", "dc.description", "DC.description", "description", "og:description")
    page.abstract = abstract
    page.doi = _meta(soup, "citation_doi", "dc.identifier", "DC.identifier")
    page.venue = _meta(soup, "citation_journal_title", "citation_conference_title", "dc.source")
    page.year = parse_year(_meta(soup, "citation_publication_date", "citation_date", "dc.date", "article:published_time"))
    page.keywords = [k.strip() for k in re.split(r"[,;，；]", _meta(soup, "citation_keywords", "keywords")) if k.strip()]
    page.pdf_url = _meta(soup, "citation_pdf_url")

    # ---- 正文与关键片段
    body_text = ""
    try:
        from readability import Document

        doc = Document(html)
        body_text = clean_text(strip_html(doc.summary()))
    except Exception:  # noqa: BLE001
        body_text = clean_text(soup.get_text(" ", strip=True))
    page.text = body_text

    page.snippets = _extract_snippets(body_text or abstract, keywords, limit=5)
    if not page.title and body_text:
        page.title = body_text.split("\n")[0][:200]
    return page


def _extract_snippets(text: str, keywords: list[str], limit: int = 5) -> list[dict]:
    """按关键词命中率挑关键片段（不改变原文内容）。"""
    sentences = [s.strip() for s in _SENT_SPLIT.split(text) if len(s.strip()) > 20]
    scored = []
    for sent in sentences[:400]:
        low = sent.lower()
        hits = sum(1 for k in keywords if k.lower() in low)
        scored.append((hits, sent))
    scored.sort(key=lambda x: (-x[0], -len(x[1])))
    out = []
    for hits, sent in scored:
        if not hits or len(out) >= limit:
            break
        out.append({"text": sent[:400], "section": "正文", "page": None})
    return out
