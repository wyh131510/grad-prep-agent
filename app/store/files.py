# -*- coding: utf-8 -*-
"""本地文件存储：源文件下载、图表图片保存（全部落在用户指定的下载目录）。"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

import httpx

from ..config import get_download_dir
from ..utils import ensure_dir, safe_filename


def paper_dir(task_id: str, paper_id: str) -> Path:
    return ensure_dir(get_download_dir() / task_id / paper_id)


def rel_path(task_id: str, paper_id: str, filename: str) -> str:
    """返回相对 download_dir 的路径（用于 API 预览与数据库存储）。"""
    return f"{task_id}/{paper_id}/{filename}"


def _candidate_urls(paper) -> list[str]:
    urls = []
    for u in (paper.pdf_url,):
        if u:
            urls.append(u)
    if paper.arxiv_id:
        urls.append(f"https://arxiv.org/pdf/{paper.arxiv_id}")
    elif paper.url and "arxiv.org" in paper.url:
        # 从 abs/详情页 URL 解析出 PDF 直链（导入/直链文献常见）
        m = re.search(r"arxiv\.org/(?:abs|pdf)/([0-9.]+)", paper.url)
        if m:
            urls.append(f"https://arxiv.org/pdf/{m.group(1)}")
    if paper.doi:
        # 优先 Unpaywall：很多"看起来付费"的论文其实有合法的免费版本
        uw = unpaywall_pdf_url(paper.doi)
        if uw:
            urls.append(uw)
        urls.append(f"https://doi.org/{paper.doi}")  # 兜底：出版方页面
    # PubMed 文献：优先走 PMC OA 开放获取 PDF（比来源页更可靠）
    if paper.source == "pubmed" and paper.url and "pubmed.ncbi.nlm.nih.gov" in paper.url:
        urls.append(_pmc_oa_url(paper.url))
    return list(dict.fromkeys(u for u in urls if u))


def has_pdf_candidates(paper) -> bool:
    """该文献是否存在可尝试的下载源（无任何源 = 付费文献，无需标记网络性失败）。"""
    return len(_candidate_urls(paper)) > 0


def unpaywall_pdf_url(doi: str) -> str | None:
    """Unpaywall 开放获取库：通过 DOI 找到合法免费 PDF 直链。"""
    if not doi:
        return None
    try:
        resp = httpx.get(
            f"https://api.unpaywall.org/v2/{doi}?email=grad-prep-agent@example.com",
            timeout=20,
            headers=_OA_HEADERS,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        loc = data.get("best_oa_location") or {}
        return loc.get("url_for_pdf") or loc.get("url") or ""
    except Exception:  # noqa: BLE001
        return None


_PDF_MAGIC = (b"%PDF-", b"%\xd0\xcf\x11\xe0")  # PDF / 可能的旧式头


def _is_pdf_file(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            head = f.read(8)
        return head.startswith(_PDF_MAGIC)
    except Exception:  # noqa: BLE001
        return False


def download_pdf(paper, job=None) -> str | None:
    """下载文献源文件到本地；返回相对路径，失败返回 None。
    逐个候选源、每个候选最多尝试 2 次；写入到临时 .part 文件后原子替换最终文件，
    避免出现 0KB 或中途被占用的半成品；下载过程通过 job.update 上报百分比进度。"""
    import time

    d = paper_dir(paper.task_id, paper.id)
    target = d / f"{safe_filename(paper.title)}.pdf"
    part = d / (target.name + ".part")
    timeout = httpx.Timeout(60, read=120, write=60, connect=20, pool=60)
    try:
        for url in _candidate_urls(paper):
            for attempt in range(2):
                try:
                    with httpx.Client(
                        timeout=timeout, follow_redirects=True,
                        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) grad-prep-agent/0.1"},
                    ) as client:
                        with client.stream("GET", url) as resp:
                            if resp.status_code >= 400:
                                break  # 该候选不可用，换下一个
                            total = int(resp.headers.get("content-length") or 0)
                            size = 0
                            last_pct = -1
                            with open(part, "wb") as f:
                                for chunk in resp.iter_bytes(64 * 1024):
                                    size += len(chunk)
                                    if size > 60 * 1024 * 1024:  # 60MB 上限
                                        break
                                    f.write(chunk)
                                    if job and total > 0:
                                        pct = int(size * 100 / total)
                                        if pct >= last_pct + 5:
                                            last_pct = pct
                                            job.update(message=f"下载中 {pct}%（{size / 1e6:.1f}/{total / 1e6:.1f} MB）")
                            if 1024 < size and _is_pdf_file(part):
                                part.replace(target)  # 原子替换，避免半成品
                                if job:
                                    job.update(message="PDF 下载完成，正在解析…")
                                return rel_path(paper.task_id, paper.id, target.name)
                            part.unlink(missing_ok=True)
                except Exception:  # noqa: BLE001
                    part.unlink(missing_ok=True)
                time.sleep(1.0 + attempt * 1.5)
    finally:
        part.unlink(missing_ok=True)
    return None


_OA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/xml,text/xml,text/html,*/*;q=0.8",
}

# Unpaywall 要求使用真实邮箱（example.com 等占位域名会被 422 拒绝）；可用环境变量覆盖
_UNPAYWALL_EMAIL = os.environ.get("UNPAYWALL_EMAIL", "grad-prep-agent@163.com")


def unpaywall_pdf_url(doi: str) -> str | None:
    """Unpaywall 开放获取库：通过 DOI 找到合法免费 PDF 直链。"""
    if not doi:
        return None
    try:
        resp = httpx.get(
            f"https://api.unpaywall.org/v2/{doi}?email={_UNPAYWALL_EMAIL}",
            timeout=20,
            headers=_OA_HEADERS,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        loc = data.get("best_oa_location") or {}
        return loc.get("url_for_pdf") or loc.get("url") or ""
    except Exception:  # noqa: BLE001
        return None


def _pmc_oa_url(pubmed_url: str) -> str | None:
    """通过 PMC OA 服务解析 PubMed 文献的开放获取 PDF 直链。"""
    import re

    m = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", pubmed_url)
    if not m:
        return None
    pmid = m.group(1)
    try:
        resp = httpx.get(
            f"https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id={pmid}&format=pdf",
            timeout=25,
            headers=_OA_HEADERS,
        )
        if resp.status_code != 200:
            return None
        m2 = re.search(r'<link[^>]+format="pdf"[^>]+href="([^"]+)"', resp.text, re.I)
        return m2.group(1).replace("&amp;", "&") if m2 else None
    except Exception:  # noqa: BLE001
        return None


def save_figure_image(task_id: str, paper_id: str, img_bytes: bytes, idx: int, ext: str = "png") -> str:
    d = paper_dir(task_id, paper_id)
    name = f"fig_{idx + 1}.{ext}"
    (d / name).write_bytes(img_bytes)
    return rel_path(task_id, paper_id, name)


def remove_task_dir(task_id: str) -> None:
    p = get_download_dir() / task_id
    if p.exists():
        shutil.rmtree(p, ignore_errors=True)


def remove_paper_dir(task_id: str, paper_id: str) -> None:
    """删除单篇文献的本地目录（含 PDF 与图片），仅限其自身文件夹，防误删。
    若删除后所在任务文件夹已空，则一并清理该空文件夹（避免残留空壳目录）。"""
    from ..utils import is_within

    base = get_download_dir().resolve()
    target = (base / task_id / paper_id).resolve()
    if is_within(base, target) and target.exists() and target != base:
        shutil.rmtree(target, ignore_errors=True)
    task_dir = (base / task_id).resolve()
    if is_within(base, task_dir) and task_dir.exists() and task_dir != base:
        try:
            if not any(task_dir.iterdir()):  # 空目录才删，绝不误删仍有文件的目录
                task_dir.rmdir()
        except OSError:
            pass
