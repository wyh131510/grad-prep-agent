# -*- coding: utf-8 -*-
"""从学术网页提取真实图注与图片，存入本地文献目录。
只接受「确凿来自该文献」的图源，避免广告、图标等噪音：
  - PubMed/PMC：NCBI 图片 CDN（pmc/blobs）或带 Figure N 图注的图片
  - arXiv：ar5iv 在线 HTML 版（figure + figcaption + /html/assets/ 图片）
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

import httpx

from ..store import files
from ..utils import clean_text, make_soup, truncate
from .common import FigureInfo

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 grad-prep-agent/0.1"
_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
}
_FIG_CAP = re.compile(r"(fig(?:ure)?\.?\s*\d+|图\s*\d+|table\s*\d+)", re.I)
_BAD_SRC = re.compile(r"logo|icon|avatar|spacer|pixel|1x1|badge|banner|sprite|blank|data:image", re.I)


def _candidate_caption(img) -> str:
    fig = img.find_parent("figure")
    if fig:
        cap = fig.find("figcaption")
        if cap:
            return clean_text(cap.get_text(" ", strip=True))
    card = img.find_parent(class_=re.compile(r"figure|caption", re.I))
    if card:
        # 只在卡片内找明确的 caption/legend 元素（避免把 img 自身的 figure-* class 误判）
        cap_el = card.find(class_=re.compile(r"(?:^|[-_])(caption|legend)(?:$|[-_ ])", re.I))
        if cap_el:
            return clean_text(cap_el.get_text(" ", strip=True))
    return clean_text(img.get("alt", ""))


def _collect_candidates(html: str) -> list[tuple[str, str]]:
    """返回 (图片 URL, 图注) 列表（按出现顺序，去重）。"""
    soup = make_soup(html)
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for img in soup.find_all("img"):
        src = (img.get("src") or img.get("data-src") or img.get("data-original") or "").strip()
        if not src or src.startswith("data:") or src.startswith("blob:"):
            continue
        if src.startswith("//"):
            src = "https:" + src
        if not src.startswith("http"):
            continue
        if _BAD_SRC.search(src):
            continue
        caption = _candidate_caption(img)
        # 严格的来源白名单：NCBI 图床（PMC 全文图）或带 Figure N 图注的图片
        is_ncbi = "pmc/blobs" in src or "cdn.ncbi.nlm.nih.gov" in src
        is_captioned = bool(_FIG_CAP.match(caption) or _FIG_CAP.search(caption))
        if not (is_ncbi or is_captioned):
            continue
        if src in seen:
            continue
        seen.add(src)
        out.append((src, truncate(caption, 300)))
    return out


def _collect_ar5iv_candidates(html: str) -> list[tuple[str, str]]:
    """ar5iv（arXiv 在线 HTML 版）：figure 标签内的图片 + figcaption 图注。"""
    soup = make_soup(html)
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    base = "https://ar5iv.labs.arxiv.org/"
    for fig in soup.find_all("figure"):
        img = fig.find("img")
        if not img:
            continue
        src = (img.get("data-src") or img.get("src") or "").strip()
        if not src or src.startswith("data:") or src.startswith("blob:"):
            continue
        src = urljoin(base, src) if not src.startswith("http") else src
        if "/assets/" not in src and "ar5iv" not in src:
            continue
        if _BAD_SRC.search(src):
            continue
        cap = fig.find("figcaption")
        caption = clean_text(cap.get_text(" ", strip=True)) if cap else ""
        if not caption:
            caption = clean_text(img.get("alt", ""))
        if src in seen:
            continue
        seen.add(src)
        out.append((src, truncate(caption, 300)))
    return out


def _save_figures(candidates: list[tuple[str, str]], client, paper, max_figures: int) -> list[FigureInfo]:
    """下载候选图并保存到本地文献目录；返回 FigureInfo 列表。"""
    figures: list[FigureInfo] = []
    for i, (src, caption) in enumerate(candidates[:max_figures]):
        try:
            img_resp = client.get(src, timeout=30)
            if img_resp.status_code >= 400 or len(img_resp.content) < 4000:
                continue
            if len(img_resp.content) > 20 * 1024 * 1024:
                continue
            ext = (src.rsplit(".", 1)[-1] if "." in src else "png").lower().split("?")[0]
            if ext not in ("png", "jpg", "jpeg", "gif", "webp", "svg"):
                ext = "png"
            rel = files.save_figure_image(paper.task_id, paper.id, img_resp.content, i, ext)
            figures.append(FigureInfo(caption=caption, description=caption, image=rel))
        except Exception:  # noqa: BLE001 单张失败跳过
            continue
    return figures


def _get_page(url: str, timeout: int):
    """抓取页面；失败返回 None。"""
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=_HEADERS) as client:
            resp = client.get(url)
            if resp.status_code >= 400:
                return None, None
            return client, resp.text
    except Exception:  # noqa: BLE001
        return None, None


def fetch_page_figures(paper, max_figures: int = 6, timeout: int = 25) -> list[FigureInfo]:
    """抓取来源页（PubMed/PMC 等）的真实图表图片并保存到本地。"""
    if not paper.url:
        return []
    client, html = _get_page(paper.url, timeout)
    if client is None or not html:
        return []
    try:
        return _save_figures(_collect_candidates(html), client, paper, max_figures)
    except Exception:  # noqa: BLE001
        return []
    finally:
        client.close()


def fetch_ar5iv_figures(paper, arxiv_id: str, max_figures: int = 6, timeout: int = 30) -> list[FigureInfo]:
    """回退路径：从 arXiv 在线 HTML 版（ar5iv）提取真实图表。"""
    if not arxiv_id:
        return []
    url = f"https://ar5iv.labs.arxiv.org/html/{arxiv_id}"
    client, html = _get_page(url, timeout)
    if client is None or not html:
        return []
    try:
        return _save_figures(_collect_ar5iv_candidates(html), client, paper, max_figures)
    except Exception:  # noqa: BLE001
        return []
    finally:
        client.close()
