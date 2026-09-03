# -*- coding: utf-8 -*-
"""统一收敛：SearchHit / 解析结果 → Paper 标准结构（清洗 + 补全）。"""
from __future__ import annotations

from ..schemas import Paper, Snippet
from ..utils import clean_text, make_id, now_iso, parse_year, truncate
from .common import ParsedPage


def _norm_title(title: str) -> str:
    """标题归一化（用于去重 id）。"""
    return clean_text(title).lower().strip(" .")


def hit_to_paper(hit, task_id: str) -> Paper:
    title = clean_text(hit.title)
    norm = _norm_title(title)
    pid = make_id(f"paper|{norm}|{hit.doi or hit.arxiv_id or hit.url}", length=16)
    return Paper(
        id=f"p_{pid}",
        task_id=task_id,
        title=title,
        authors=[clean_text(a) for a in hit.authors if clean_text(a)][:20],
        year=hit.year,
        venue=clean_text(hit.venue),
        source=hit.extra.get("_source", ""),
        doi=clean_text(hit.doi),
        arxiv_id=clean_text(hit.arxiv_id),
        url=hit.url,
        pdf_url=hit.pdf_url,
        abstract=truncate(clean_text(hit.abstract), 6000),
        keywords=[clean_text(k) for k in hit.keywords if clean_text(k)][:10],
        citations=hit.citations,
        is_open_access=hit.is_open_access,
        created_at=now_iso(),
    )


def parsed_to_paper(parsed: ParsedPage, task_id: str, source: str, paper_id: str = "") -> Paper:
    title = clean_text(parsed.title) or "（未识别标题）"
    pid = paper_id or f"p_{make_id(f'paper|{_norm_title(title)}|{parsed.doi or parsed.url}', length=16)}"
    snippets = [Snippet(text=s["text"], section=s.get("section", ""), page=s.get("page")) for s in parsed.snippets]
    return Paper(
        id=pid,
        task_id=task_id,
        title=title,
        authors=[clean_text(a) for a in parsed.authors if clean_text(a)][:20],
        year=parse_year(parsed.year),
        venue=clean_text(parsed.venue),
        source=source,
        doi=clean_text(parsed.doi),
        url=parsed.url,
        pdf_url=parsed.pdf_url,
        abstract=truncate(clean_text(parsed.abstract), 6000),
        keywords=[clean_text(k) for k in parsed.keywords if clean_text(k)][:10],
        snippets=snippets,
        figures=[f for f in parsed.figures if f.image or f.caption],
        created_at=now_iso(),
    )


def merge_paper(old: Paper, new: Paper) -> Paper:
    """同 id 去重合并：保留更丰富的一侧，空字段互补。"""
    for field in (
        "abstract", "pdf_url", "url", "venue", "doi", "arxiv_id", "title_zh", "abstract_zh",
    ):
        if not getattr(old, field) and getattr(new, field):
            setattr(old, field, getattr(new, field))
    if not old.authors and new.authors:
        old.authors = new.authors
    if not old.keywords and new.keywords:
        old.keywords = new.keywords
    if old.year is None and new.year is not None:
        old.year = new.year
    if (old.citations or 0) < (new.citations or 0):
        old.citations = new.citations
    if not old.snippets and new.snippets:
        old.snippets = new.snippets
    if not old.figures and new.figures:
        old.figures = new.figures
    if new.is_open_access:
        old.is_open_access = True
    return old
