# -*- coding: utf-8 -*-
"""开题报告接口：模板上传、分块生成/修改、导出。"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from ..agents import proposal as proposal_agent
from ..jobs import manager
from ..store import repo
from ..utils import safe_filename

router = APIRouter(tags=["proposal"])


class GenerateRequest(BaseModel):
    instruction: str = ""


class SectionUpdate(BaseModel):
    content: str


def _get_task(task_id: str):
    task = repo.get_task(task_id)
    if task is None:
        raise HTTPException(404, "任务不存在")
    return task


@router.post("/tasks/{task_id}/template")
async def upload_template(task_id: str, file: UploadFile = File(...)) -> dict:
    task = _get_task(task_id)
    data = await file.read()
    if not data:
        raise HTTPException(400, "文件为空")
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(400, "文件过大（>10MB）")
    try:
        info = proposal_agent.parse_template_file(file.filename or "template.docx", data)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    repo.save_template(task_id, info)
    repo.ensure_sections(task_id, proposal_agent.DEFAULT_SECTIONS)
    return info.model_dump()


@router.get("/tasks/{task_id}/template")
def get_template(task_id: str) -> dict:
    _get_task(task_id)
    info = repo.get_template(task_id)
    if not info:
        raise HTTPException(404, "尚未上传学校模板")
    return info.model_dump()


@router.get("/tasks/{task_id}/proposal")
def get_proposal(task_id: str) -> dict:
    _get_task(task_id)
    return {"sections": [s.model_dump() for s in proposal_agent.get_sections(task_id)]}


@router.post("/tasks/{task_id}/proposal/sections/{key}/generate")
def generate_section(task_id: str, key: str, body: GenerateRequest) -> dict:
    task = _get_task(task_id)
    job = manager.start(
        "proposal_section", f"生成分块：{key}",
        lambda j: {"key": key, "content": proposal_agent.generate_section(task, key, body.instruction or "", j)},
    )
    return {"job_id": job.id}


@router.put("/tasks/{task_id}/proposal/sections/{key}")
def update_section(task_id: str, key: str, body: SectionUpdate) -> dict:
    _get_task(task_id)
    sections = {s.key: s for s in repo.get_sections(task_id)}
    if key not in sections:
        raise HTTPException(404, f"未知分块：{key}")
    s = sections[key]
    repo.put_section(task_id, key, s.title, body.content, "edited" if body.content.strip() else "empty")
    return {"key": key, "title": s.title, "content": body.content, "status": "edited" if body.content.strip() else "empty"}


@router.post("/tasks/{task_id}/proposal/generate_all")
def generate_all(task_id: str) -> dict:
    task = _get_task(task_id)
    job = manager.start(
        "proposal_all", "分块生成开题报告",
        lambda j: proposal_agent.generate_all(task, j),
    )
    return {"job_id": job.id}


@router.get("/tasks/{task_id}/proposal/export")
def export_proposal(task_id: str, format: str = "md") -> Response:
    task = _get_task(task_id)
    name = safe_filename(f"{task.topic}_开题报告")
    if format == "docx":
        data = proposal_agent.export_docx(task)
        disposition = f"attachment; filename*=UTF-8''{quote(name + '.docx')}"
        return Response(
            data,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": disposition},
        )
    text = proposal_agent.export_markdown(task)
    disposition = f"attachment; filename*=UTF-8''{quote(name + '.md')}"
    return Response(text, media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": disposition})
