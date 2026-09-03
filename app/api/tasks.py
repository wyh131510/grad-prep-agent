# -*- coding: utf-8 -*-
"""任务（调研项目）相关接口。"""
from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from ..jobs import manager
from ..schemas import TaskCreate, TaskUpdate
from ..store import files, repo
from ..search import engine

router = APIRouter(tags=["tasks"])


class SearchRequest(BaseModel):
    feedback: str = ""


def _get_task(task_id: str):
    task = repo.get_task(task_id)
    if task is None:
        raise HTTPException(404, "任务不存在")
    return task


@router.post("/tasks")
def create_task(body: TaskCreate) -> dict:
    if not body.topic.strip():
        raise HTTPException(400, "选题不能为空")
    return repo.create_task(body).model_dump()


@router.get("/tasks")
def list_tasks() -> list[dict]:
    return [t.model_dump() for t in repo.list_tasks()]


@router.get("/tasks/{task_id}")
def get_task(task_id: str) -> dict:
    return _get_task(task_id).model_dump()


@router.put("/tasks/{task_id}")
def update_task(task_id: str, body: TaskUpdate) -> dict:
    """编辑任务参数（年份范围、来源、选题、专业等），便于调整后重新检索。"""
    _get_task(task_id)
    fields = body.model_dump(exclude_unset=True)
    if fields.get("topic") is not None and not str(fields["topic"]).strip():
        raise HTTPException(400, "选题不能为空")
    updated = repo.update_task(task_id, fields)
    return updated.model_dump()


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str) -> dict:
    _get_task(task_id)
    repo.delete_task(task_id)
    files.remove_task_dir(task_id)
    return {"ok": True}


@router.post("/tasks/{task_id}/search")
def start_search(task_id: str, body: SearchRequest) -> dict:
    task = _get_task(task_id)
    job = manager.start(
        "search",
        f"文献检索：{task.topic[:30]}",
        lambda j: engine.run_search_pipeline(task, body.feedback or "", j),
    )
    return {"job_id": job.id}


@router.get("/tasks/{task_id}/plan")
def get_plan(task_id: str) -> dict:
    task = _get_task(task_id)
    if not task.plan:
        raise HTTPException(404, "尚未生成检索计划，请先启动检索")
    return task.plan


@router.post("/tasks/{task_id}/import")
async def import_literature(task_id: str, file: UploadFile = File(...)) -> dict:
    """导入知网/万方等导出的 EndNote/RIS 文本文件。"""
    task = _get_task(task_id)
    data = await file.read()
    if not data:
        raise HTTPException(400, "文件为空")
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(400, "文件过大（>5MB）")
    job = manager.start(
        "import",
        f"导入文献：{file.filename}",
        lambda j: engine.import_documents(task, file.filename or "import.txt", data, j),
    )
    return {"job_id": job.id}
