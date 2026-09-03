# -*- coding: utf-8 -*-
"""评审与答辩接口。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..agents import defense as defense_agent
from ..agents import review as review_agent
from ..db import db
from ..jobs import manager
from ..store import repo

router = APIRouter(tags=["review"])


class ApplyRequest(BaseModel):
    section: str
    instruction: str = ""


def _get_task(task_id: str):
    task = repo.get_task(task_id)
    if task is None:
        raise HTTPException(404, "任务不存在")
    return task


@router.post("/tasks/{task_id}/review")
def start_review(task_id: str) -> dict:
    task = _get_task(task_id)
    job = manager.start(
        "review", f"多智能体评审：{task.topic[:30]}",
        lambda j: review_agent.run_review(task, j),
    )
    return {"job_id": job.id}


@router.get("/tasks/{task_id}/review")
def get_review(task_id: str) -> dict:
    _get_task(task_id)
    results = repo.get_reviews(task_id)
    merged = repo.get_merged(task_id)
    if not results or not merged:
        raise HTTPException(404, "尚未评审，请先启动多智能体评审")
    row = db.query_one("SELECT created_at FROM reviews WHERE task_id = ? AND agent = 'merged'", (task_id,))
    created = row["created_at"] if row else ""
    return {"results": [r.model_dump() for r in results], "merged": merged.model_dump(), "created_at": created}


@router.post("/tasks/{task_id}/review/apply")
def apply_review(task_id: str, body: ApplyRequest) -> dict:
    task = _get_task(task_id)
    # 路由层先校验分块：overall（整体性意见）需指定具体分块，给出明确指引而非神秘报错
    from ..agents import proposal as proposal_agent

    valid = {s.key for s in proposal_agent.get_sections(task_id)}
    if body.section not in valid:
        raise HTTPException(
            400,
            f"该意见为整体性意见（overall），请先选择要修改的具体分块（可选：{', '.join(valid)}）再执行修改",
        )
    job = manager.start(
        "review_apply", f"按评审意见修改：{body.section}",
        lambda j: review_agent.apply_review(task, body.section, body.instruction or "", j),
    )
    return {"job_id": job.id}


@router.post("/tasks/{task_id}/defense")
def start_defense(task_id: str) -> dict:
    task = _get_task(task_id)
    job = manager.start(
        "defense", f"答辩问题清单：{task.topic[:30]}",
        lambda j: {"content": defense_agent.generate_defense(task, j)},
    )
    return {"job_id": job.id}


@router.get("/tasks/{task_id}/defense")
def get_defense(task_id: str) -> dict:
    _get_task(task_id)
    data = repo.get_defense(task_id)
    if not data or not data.get("content"):
        raise HTTPException(404, "尚未生成答辩问题清单")
    return data
