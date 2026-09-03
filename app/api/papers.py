# -*- coding: utf-8 -*-
"""文献接口：列表筛选、收藏下载、单篇总结、翻译、调研综述、全文解析。"""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..agents import summary as summary_agent
from ..agents import translate as translate_agent
from ..jobs import manager
from ..store import files, repo

router = APIRouter(tags=["papers"])


class CollectRequest(BaseModel):
    download: bool = True


class BulkCollectRequest(BaseModel):
    paper_ids: list[str]
    download: bool = True


class SurveyRequest(BaseModel):
    paper_ids: list[str]


def _get_paper(paper_id: str):
    paper = repo.get_paper(paper_id)
    if paper is None:
        raise HTTPException(404, "文献不存在")
    return paper


def _get_task(task_id: str):
    task = repo.get_task(task_id)
    if task is None:
        raise HTTPException(404, "任务不存在")
    return task


@router.get("/papers")
def list_all_papers(
    q: str = "",
    task_id: Optional[str] = None,
    collected: Optional[bool] = None,
    sort: str = "score",
    order: str = "desc",
    limit: int = 200,
    offset: int = 0,
) -> dict:
    """跨任务的全局文献列表（文献库页使用，可按 task_id 过滤）。"""
    limit = max(1, min(limit, 500))
    total, items = repo.list_papers(
        task_id or None, q=q, collected=collected, sort=sort, order=order, limit=limit, offset=offset
    )
    return {"total": total, "items": [p.model_dump() for p in items]}


@router.get("/tasks/{task_id}/papers")
def list_papers(
    task_id: str,
    q: str = "",
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    source: str = "",
    collected: Optional[bool] = None,
    sort: str = "score",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    _get_task(task_id)
    limit = max(1, min(limit, 200))
    total, items = repo.list_papers(
        task_id, q=q, year_from=year_from, year_to=year_to, source=source,
        collected=collected, sort=sort, order=order, limit=limit, offset=offset,
    )
    return {"total": total, "items": [p.model_dump() for p in items]}


@router.get("/papers/{paper_id}")
def get_paper(paper_id: str) -> dict:
    return _get_paper(paper_id).model_dump()


def _parse_pdf_into_paper(paper, rel_path: str) -> int:
    """解析已下载的 PDF，把关键片段/图表写回文献。返回写回字段数。"""
    from ..config import get_download_dir
    from ..parse import pdf_parser

    data = (get_download_dir() / rel_path).read_bytes()
    parsed = pdf_parser.parse_pdf(
        data, paper.task_id, paper.id, keywords=[], url=paper.url, pdf_url=paper.pdf_url
    )
    changed = 0
    if parsed.snippets:
        paper.snippets = parsed.snippets
        changed += 1
    if parsed.figures:
        paper.figures = parsed.figures
        changed += 1
    if changed:
        repo.upsert_paper(paper)
    return changed


def _collect_job(task, paper_ids: list[str], download: bool, job) -> dict:
    from ..parse.page_figures import fetch_ar5iv_figures, fetch_page_figures

    collected = downloaded = 0
    failed: list[dict] = []
    for i, pid in enumerate(paper_ids):
        job.update(i / max(1, len(paper_ids)), f"收藏处理中（{i + 1}/{len(paper_ids)}）…")
        paper = repo.get_paper(pid)
        if paper is None or paper.task_id != task.id:
            failed.append({"title": pid, "reason": "文献不存在或不属于该任务"})
            continue
        paper.collected = True
        if download:
            paper.download_status = "downloading"
            paper.download_note = ""
            repo.upsert_paper(paper)
            job.update(message=f"正在下载：{paper.title[:30]}…")
            rel = files.download_pdf(paper, job=job)
            if rel:
                paper.file_path = rel
                paper.download_status = "done"
                paper.download_note = ""
                repo.upsert_paper(paper)
                downloaded += 1
                if not paper.snippets and not paper.figures:
                    try:
                        _parse_pdf_into_paper(paper, rel)
                    except Exception as exc:  # noqa: BLE001
                        failed.append({"title": paper.title[:60], "reason": f"全文解析失败：{exc}"})
            else:
                # 下载失败：区分"无免费全文（付费文献）"与"网络性问题"，并尝试备用图源
                if files.has_pdf_candidates(paper):
                    paper.download_status = "failed"
                    paper.download_note = "PDF 下载失败（网络或源站限制，可稍后重试）"
                else:
                    paper.download_status = "failed"
                    paper.download_note = "该文献无免费全文来源（可能为付费文献，可到学校图书馆/知网获取）"
                repo.upsert_paper(paper)
                figs: list = []
                aid = paper.arxiv_id or ""
                if not aid and paper.url and "arxiv.org" in paper.url:
                    m = re.search(r"arxiv\.org/(?:abs|pdf)/([0-9.]+)", paper.url or "")
                    aid = m.group(1) if m else ""
                if aid:
                    figs = fetch_ar5iv_figures(paper, aid, max_figures=3)
                if not figs:
                    figs = fetch_page_figures(paper, max_figures=3)
                if figs:
                    paper.figures = figs
                    paper.download_note = "无开放获取 PDF，已从在线版本提取图表"
                    repo.upsert_paper(paper)
                failed.append({"title": paper.title[:60], "reason": paper.download_note})
        else:
            paper.download_status = "none"
            repo.upsert_paper(paper)
        collected += 1
    return {"collected": collected, "downloaded": downloaded, "failed": failed}


@router.post("/papers/{paper_id}/collect")
def collect_paper(paper_id: str, body: CollectRequest) -> dict:
    paper = _get_paper(paper_id)
    job = manager.start(
        "collect", f"收藏：{paper.title[:30]}",
        lambda j: _collect_job(_get_task(paper.task_id), [paper_id], body.download, j),
    )
    return {"job_id": job.id}


@router.delete("/papers/{paper_id}/collect")
def uncollect_paper(paper_id: str) -> dict:
    """取消收藏：同时删除该文献的本地文件与图片目录（仅限其自身文件夹）。"""
    paper = _get_paper(paper_id)
    repo.set_paper_collected(paper_id, False, "")
    files.remove_paper_dir(paper.task_id, paper_id)
    return {"ok": True}


@router.post("/papers/{paper_id}/parse_fulltext")
def parse_fulltext(paper_id: str) -> dict:
    """按需解析全文：下载 PDF 提取关键片段与图表；无 PDF 时从来源页提取真实图表。"""
    paper = _get_paper(paper_id)

    def _job(job) -> dict:
        import re

        from ..config import get_download_dir
        from ..parse import pdf_parser
        from ..parse.page_figures import fetch_ar5iv_figures, fetch_page_figures

        notes: list[str] = []
        rel = None
        pdf_data = None
        download_attempted = False
        job.update(0.15, "获取文献全文源…")
        if not paper.file_path:
            download_attempted = True
            paper.download_status = "downloading"
            paper.download_note = ""
            repo.upsert_paper(paper)
            rel = files.download_pdf(paper, job=job)
            if rel:
                paper.collected = True
                paper.file_path = rel
                paper.download_status = "done"
                paper.download_note = ""
                repo.upsert_paper(paper)
                job.update(message="已下载全文 PDF")
            else:
                if files.has_pdf_candidates(paper):
                    paper.download_status = "failed"
                    paper.download_note = "PDF 下载失败（网络或源站限制）"
                else:
                    paper.download_status = "failed"
                    paper.download_note = "该文献无免费全文来源（可能为付费文献，可到学校图书馆/知网获取）"
                repo.upsert_paper(paper)
                job.update(message="PDF 下载失败，尝试备份来源提取")
        if paper.file_path and not rel:
            rel = paper.file_path
        if rel:
            try:
                pdf_data = (get_download_dir() / rel).read_bytes()
            except Exception:  # noqa: BLE001
                pdf_data = None
        if pdf_data:
            job.update(0.4, "解析 PDF：正文、关键片段、图注与表格…")
            parsed = pdf_parser.parse_pdf(
                pdf_data, paper.task_id, paper.id, keywords=[], url=paper.url, pdf_url=paper.pdf_url
            )
            if parsed.snippets:
                paper.snippets = parsed.snippets
                notes.append(f"提取关键片段 {len(parsed.snippets)} 条")
            if parsed.figures:
                paper.figures = parsed.figures
                notes.append(f"提取真实图表 {len(parsed.figures)} 张")
            if parsed.note:
                notes.append(parsed.note)
            if parsed.tables:
                notes.append(f"提取表格 {len(parsed.tables)} 张")
        if not paper.snippets and not paper.figures:
            if download_attempted and not pdf_data:
                notes.append("PDF 下载失败（网络波动或源站限流），改用备选来源提取")
            # 回退 1：arXiv 在线 HTML 版（ar5iv）
            aid = paper.arxiv_id or ""
            if not aid and paper.url:
                m = re.search(r"arxiv\.org/(?:abs|pdf)/([0-9.]+)", paper.url or "")
                aid = m.group(1) if m else ""
            if aid:
                job.update(0.55, "尝试从 arXiv 在线版本提取图表…")
                figs = fetch_ar5iv_figures(paper, aid, max_figures=6)
                if figs:
                    paper.figures = figs
                    notes.append(f"从 arXiv 在线版本提取真实图表 {len(figs)} 张")
            # 回退 2：PubMed/PMC 来源页
            if not paper.figures and paper.url and ("pubmed" in paper.url.lower() or "pmc" in paper.url.lower()):
                job.update(0.65, "从来源页提取真实图表…")
                figs = fetch_page_figures(paper, max_figures=6)
                if figs:
                    paper.figures = figs
                    notes.append(f"从来源页提取真实图表 {len(figs)} 张")
        changed = bool(paper.snippets or paper.figures)
        if rel:
            paper.download_status = "done"
            paper.download_note = ""
        if changed or rel:
            repo.upsert_paper(paper)
        job.update(0.97, "解析完成。")
        return {
            "snippets": len(paper.snippets),
            "figures": len(paper.figures),
            "file_path": rel or paper.file_path,
            "notes": notes,
            "status": "ok" if changed else "no_content",
        }

    job = manager.start("parse_fulltext", f"解析全文：{paper.title[:30]}", _job)
    return {"job_id": job.id}


@router.post("/tasks/{task_id}/papers/collect")
def bulk_collect(task_id: str, body: BulkCollectRequest) -> dict:
    task = _get_task(task_id)
    if not body.paper_ids:
        raise HTTPException(400, "未选择文献")
    job = manager.start(
        "collect", f"批量收藏 {len(body.paper_ids)} 篇",
        lambda j: _collect_job(task, body.paper_ids, body.download, j),
    )
    return {"job_id": job.id}


@router.post("/papers/{paper_id}/summarize")
def summarize_paper(paper_id: str) -> dict:
    paper = _get_paper(paper_id)
    task = _get_task(paper.task_id)
    job = manager.start(
        "summarize", f"总结：{paper.title[:30]}",
        lambda j: summary_agent.summarize_paper(paper, task, j).model_dump(),
    )
    return {"job_id": job.id}


@router.post("/papers/{paper_id}/translate")
def translate_paper(paper_id: str) -> dict:
    paper = _get_paper(paper_id)
    task = _get_task(paper.task_id)
    job = manager.start(
        "translate", f"翻译：{paper.title[:30]}",
        lambda j: translate_agent.translate_paper(paper, task, j).model_dump(),
    )
    return {"job_id": job.id}


@router.post("/tasks/{task_id}/survey")
def create_survey(task_id: str, body: SurveyRequest) -> dict:
    task = _get_task(task_id)
    if not body.paper_ids:
        raise HTTPException(400, "未选择文献")
    job = manager.start(
        "survey", f"调研综述（{len(body.paper_ids)} 篇）",
        lambda j: summary_agent.generate_survey(task, body.paper_ids, j),
    )
    return {"job_id": job.id}


@router.get("/tasks/{task_id}/survey")
def get_survey(task_id: str) -> dict:
    _get_task(task_id)
    survey = repo.get_survey(task_id)
    if not survey or not survey.get("content"):
        raise HTTPException(404, "尚未生成调研综述")
    return survey
