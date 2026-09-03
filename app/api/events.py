# -*- coding: utf-8 -*-
"""后台任务查询与 SSE 进度流。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..jobs import manager
from ..utils import json_dumps

router = APIRouter(tags=["jobs"])


@router.get("/jobs")
def list_jobs(limit: int = 20) -> list[dict]:
    return [j.model_dump() for j in manager.list(limit)]


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(404, "任务不存在")
    return job.snapshot().model_dump()


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: str, request: Request) -> StreamingResponse:
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(404, "任务不存在")

    async def gen():
        last_seq = 0
        while True:
            events = job.events_after(last_seq)
            for e in events:
                last_seq = e["seq"]
                yield f"id: {e['seq']}\nevent: {e['type']}\ndata: {json_dumps(e['data'])}\n\n"
            if job.status != "running":
                break
            if await request.is_disconnected():
                break
            await asyncio.sleep(0.4)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
