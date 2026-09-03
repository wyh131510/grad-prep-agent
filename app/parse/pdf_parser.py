# -*- coding: utf-8 -*-
"""PDF 解析：PyMuPDF 提取文本/图片/图注，pdfplumber 提取表格；扫描版自动走 OCR。"""
from __future__ import annotations

import io
import re

from ..utils import clean_text, parse_year, truncate
from .common import FigureInfo, ParsedPage
from .ocr import ocr

_FIG_CAP = re.compile(r"^\s*(fig(?:ure)?\.?\s*\d+|图\s*\d+|表\s*\d+|table\s*\d+)", re.I)
_ABS_START = re.compile(r"(?i)^\s*(abstract|摘要)\s*[:：]?\s*$")
_SENT_SPLIT = re.compile(r"(?<=[.。!！?？;；:：])\s*")


def _extract_title(first_page) -> str:
    """优先 PDF 元数据，否则取首页最大字号文本行。"""
    meta = (first_page.parent.metadata or {}).get("title", "")
    meta = clean_text(meta)
    if meta and len(meta) >= 6:
        return truncate(meta, 250)
    try:
        d = first_page.get_text("dict")
        spans = []
        for block in d.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if span.get("text", "").strip():
                        spans.append((span.get("size", 0), span.get("text", "").strip()))
        if spans:
            spans.sort(key=lambda x: -x[0])
            title = " ".join(t for _, t in spans[:3])
            return truncate(clean_text(title), 250)
    except Exception:  # noqa: BLE001
        pass
    return ""


def _extract_abstract(text: str, first_page_text: str) -> str:
    m = _ABS_START.search(text)
    if m:
        seg = text[m.end():]
        stop = re.search(r"(?i)^\s*(keywords?|关键词|1\.?\s*intro)", seg, re.M)
        seg = seg[: stop.start()] if stop else seg
        return truncate(clean_text(seg), 2000)
    return truncate(clean_text(first_page_text[400:2200]), 1500)


def _extract_snippets(full_text: str, keywords: list[str], page_of_sentence, limit: int = 6) -> list[dict]:
    """按关键词命中率挑关键片段；无关键词或无命中时退化为开头信息句（保证有内容）。"""
    sentences = [s.strip() for s in _SENT_SPLIT.split(full_text) if 25 < len(s.strip()) < 600]
    out: list[dict] = []
    if keywords:
        scored = []
        for sent in sentences[:1500]:
            low = sent.lower()
            hits = sum(1 for k in keywords if k.lower() in low)
            scored.append((hits, sent))
        scored.sort(key=lambda x: (-x[0], -len(x[1])))
        for hits, sent in scored:
            if not hits or len(out) >= limit:
                break
            out.append({"text": truncate(sent, 400), "section": "全文", "page": page_of_sentence(sent)})
    if not out:
        head = [s for s in sentences[:24] if not s.lower().startswith(("abstract", "keywords", "摘要", "关键词"))][:3]
        if not head and sentences:
            head = sentences[:3]
        for sent in head:
            out.append({"text": truncate(sent, 400), "section": "开头", "page": page_of_sentence(sent)})
    return out


def _extract_figures(doc, task_id: str, paper_id: str, max_total: int = 8) -> tuple[list[FigureInfo], int]:
    """提取正文图片与图注（图注为文献原文，非 AI 生成）。"""
    from ..store.files import save_figure_image

    figures: list[FigureInfo] = []
    saved = 0
    for page_index in range(len(doc)):
        if saved >= max_total:
            break
        page = doc[page_index]
        text_blocks = [b for b in page.get_text("blocks") if b[6] == 0]  # 文本块
        for img in page.get_images(full=True):
            if saved >= max_total:
                break
            try:
                xref = img[0]
                rects = page.get_image_rects(xref)
                if not rects:
                    continue
                rect = rects[0]
                if rect.width < 120 or rect.height < 80:  # 过滤小图标
                    continue
                pix = doc.extract_image(xref)
                if not pix or pix.get("width", 0) < 120:
                    continue
                png = pix["image"]
                ext = str(pix.get("ext") or "png").lower()
                if ext not in ("png", "jpg", "jpeg", "webp"):
                    ext = "png"
                # 图注：图片下方 60pt 内、匹配 Fig/图 模式的文本块
                caption = ""
                for b in text_blocks:
                    bx0, by0, bx1, by1 = b[0], b[1], b[2], b[3]
                    if bx0 >= rect.x0 - 20 and bx1 <= rect.x1 + 120 and 0 <= by0 - rect.y1 <= 70:
                        t = clean_text(b[4])
                        if _FIG_CAP.match(t):
                            caption = truncate(t, 300)
                            break
                if not caption:  # 放宽：整页内最接近底部区域的 Fig 文本
                    for b in text_blocks:
                        t = clean_text(b[4])
                        if _FIG_CAP.match(t) and b[1] > rect.y1 - 30:
                            caption = truncate(t, 300)
                            break
                rel = save_figure_image(task_id, paper_id, png, saved, ext)
                figures.append(
                    FigureInfo(caption=caption, description=caption, page=page_index + 1, image=rel)
                )
                saved += 1
            except Exception:  # noqa: BLE001
                continue
    return figures, saved


def _extract_tables(data: bytes, max_tables: int = 3) -> list[dict]:
    tables: list[dict] = []
    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for i, page in enumerate(pdf.pages[:10]):
                if len(tables) >= max_tables:
                    break
                for t in page.extract_tables() or []:
                    if len(tables) >= max_tables or not t:
                        break
                    rows = []
                    for row in t[:12]:
                        cells = [("" if c is None else str(c)).strip().replace("\n", " ") for c in row]
                        if any(cells):
                            rows.append("| " + " | ".join(cells) + " |")
                    if rows:
                        tables.append({"text": "\n".join(rows), "page": i + 1})
    except Exception:  # noqa: BLE001
        pass
    return tables


def parse_pdf(
    data: bytes,
    task_id: str,
    paper_id: str,
    keywords: list[str] | None = None,
    url: str = "",
    pdf_url: str = "",
) -> ParsedPage:
    keywords = [k for k in (keywords or []) if k]
    page = ParsedPage(url=url, pdf_url=pdf_url)
    doc = None
    try:
        try:
            import pymupdf as fitz  # PyMuPDF >= 1.24 推荐导入名
        except ImportError:  # pragma: no cover
            import fitz  # 旧版兼容

        doc = fitz.open(stream=data, filetype="pdf")
        full_text = clean_text("\n".join(p.get_text() for p in doc))
        first_page_text = clean_text(doc[0].get_text()) if len(doc) else ""
        page.text = full_text

        page.title = _extract_title(doc[0]) if len(doc) else ""
        if len(doc):
            meta = doc.metadata or {}
            if meta.get("author"):
                page.authors = [a.strip() for a in re.split(r"[;,;]", clean_text(meta["author"])) if a.strip()]
            page.year = parse_year(meta.get("creationDate") or meta.get("modDate"))
        page.abstract = _extract_abstract(full_text, first_page_text)

        # 扫描版 PDF：无文本层时用 OCR 识别前几页
        if len(full_text) < 300 and ocr.available:
            ocr_parts = []
            for i in range(min(4, len(doc))):
                try:
                    ocr_parts.append(ocr.recognize_pdf_page(doc[i]))
                except Exception:  # noqa: BLE001
                    break
            ocr_text = clean_text("\n".join(ocr_parts))
            if ocr_text:
                page.text = ocr_text + "\n\n" + full_text
                if not page.title and ocr_text:
                    page.title = truncate(ocr_text.split("\n")[0], 250)
                if not page.abstract:
                    page.abstract = truncate(ocr_text[300:1800], 1500)
                page.note = "扫描版 PDF：已用 OCR 提取前几页文字"
        elif len(full_text) < 300:
            page.note = "扫描版 PDF：未安装 OCR（可安装 rapidocr_onnxruntime 后重新解析）"

        # 关键片段：记录每句所在页码
        page_texts = [clean_text(p.get_text()) for p in doc]

        def page_of(sentence: str) -> int | None:
            probe = sentence[:60]
            for i, t in enumerate(page_texts):
                if probe in t:
                    return i + 1
            return None

        page.snippets = _extract_snippets(page.text, keywords, page_of)
        page.figures, _ = _extract_figures(doc, task_id, paper_id)
        page.tables = _extract_tables(data)
        doc.close()
    except Exception as exc:  # noqa: BLE001
        page.note = f"PDF 解析异常：{exc}"
        if doc is not None:
            try:
                doc.close()
            except Exception:  # noqa: BLE001
                pass
    return page
