# -*- coding: utf-8 -*-
"""文献导入解析：知网等中文库导出的 EndNote / RIS 格式。"""
from __future__ import annotations

import re

from ..utils import clean_text, parse_year


def _split_records(text: str) -> list[str]:
    """EndNote txt：以 ER 行分隔（兼容 %ER）；RIS：以 ER  - 行分隔。"""
    parts = re.split(r"(?im)^\s*%?ER\s*(?:-)?\s*$", text)
    return [p for p in parts if p.strip()]


_ENDNOTE_TAGS = {
    "T": "title", "A": "authors", "J": "venue", "D": "year",
    "X": "abstract", "K": "keywords", "U": "url", "R": "doi",
}


def parse_endnote(text: str) -> list[dict]:
    """EndNote 导出格式（%T/%A/%J... 字段行 + 续行交错）。"""
    records = []
    for rec in _split_records(text):
        lines = [ln.rstrip() for ln in rec.splitlines()]
        item: dict[str, object] = {"authors": [], "keywords": []}
        field = ""
        for ln in lines:
            if ln.startswith("%"):
                field = ln[1:2].upper() if len(ln) > 1 else ""
                val = ln[2:].strip()
                if not field or not val:
                    continue
                target = _ENDNOTE_TAGS.get(field, field.lower())
                if target == "authors":
                    item["authors"].append(val)  # type: ignore[union-attr]
                elif target == "keywords":
                    item["keywords"].extend(  # type: ignore[union-attr]
                        k.strip() for k in re.split(r"[;；]", val) if k.strip()
                    )
                elif target in item:
                    item[target] = f"{item[target]} {val}".strip()
                else:
                    item[target] = val
            elif field and ln.strip():
                # 续行：附加到当前字段
                target = _ENDNOTE_TAGS.get(field, field.lower())
                if target not in ("authors", "keywords") and target in item:
                    item[target] = f"{item[target]} {ln.strip()}".strip()
        if item.get("title"):
            records.append(item)  # type: ignore[arg-type]
    return records


def parse_ris(text: str) -> list[dict]:
    """RIS 格式（TY/ER 标签）。"""
    records = []
    for rec in _split_records(text):
        item: dict[str, str] = {"authors": [], "keywords": []}
        for ln in rec.splitlines():
            m = re.match(r"^([A-Z0-9]{2})\s*-\s*(.*)$", ln)
            if not m:
                continue
            tag, value = m.group(1), m.group(2).strip()
            if tag in ("T1", "TI"):
                item["title"] = value
            elif tag == "AB":
                item["abstract"] = f"{item.get('abstract', '')} {value}".strip()
            elif tag in ("AU", "A1"):
                item["authors"].append(value)
            elif tag == "PY":
                item["year"] = value
            elif tag in ("JO", "JF", "T2"):
                item["venue"] = value
            elif tag == "DO":
                item["doi"] = value
            elif tag == "KW":
                item["keywords"].append(value)
            elif tag == "UR":
                item["url"] = value
            elif tag == "L1":
                item["pdf_url"] = value
        if item.get("title"):
            records.append(item)
    return records


def parse_import_text(text: str) -> list[dict]:
    """自动识别 EndNote / RIS，支持两种格式混合的文件。"""
    text = text.replace("\r\n", "\n")
    raw: list[dict] = []
    for rec in _split_records(text):
        head = rec.lstrip()[:200]
        if head.startswith("%"):
            raw.extend(parse_endnote(rec))
        elif re.search(r"(?im)^\s*TY\s*-", rec):
            raw.extend(parse_ris(rec))
    out = []
    for r in raw:
        out.append(
            {
                "title": clean_text(r.get("title", "")),
                "abstract": clean_text(r.get("abstract", ""))[:6000],
                "authors": [clean_text(a) for a in r.get("authors", []) if clean_text(a)][:20],
                "year": parse_year(r.get("year", "")),
                "venue": clean_text(r.get("venue", "")),
                "doi": clean_text(r.get("doi", "")),
                "keywords": [clean_text(k) for k in r.get("keywords", []) if clean_text(k)][:10],
                "url": r.get("url", ""),
                "pdf_url": r.get("pdf_url", ""),
            }
        )
    return out
