# -*- coding: utf-8 -*-
"""后台任务（Job）管理：线程池执行 + 事件队列，供 SSE 订阅进度。"""
from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from .schemas import JobSnapshot


class Job:
    def __init__(self, job_id: str, type_: str, label: str):
        self.id = job_id
        self.type = type_
        self.label = label
        self.status = "running"
        self.progress = 0.0
        self.message = label
        self.result: Any = None
        self.error: str | None = None
        self.created_at = time.time()
        self._events: list[dict] = []
        self._lock = threading.Lock()

    def update(self, progress: float | None = None, message: str | None = None) -> None:
        with self._lock:
            if progress is not None:
                self.progress = max(0.0, min(1.0, float(progress)))
            if message:
                self.message = message
            self._events.append(
                {
                    "seq": len(self._events) + 1,
                    "type": "log",
                    "data": {"progress": self.progress, "message": self.message},
                }
            )

    def set_result(self, data: Any) -> None:
        with self._lock:
            self.status = "done"
            self.progress = 1.0
            self.result = data
            self._events.append({"seq": len(self._events) + 1, "type": "result", "data": data})

    def fail(self, message: str) -> None:
        with self._lock:
            self.status = "error"
            self.error = message
            self._events.append({"seq": len(self._events) + 1, "type": "error", "data": {"message": message}})

    def events_after(self, after_seq: int) -> list[dict]:
        with self._lock:
            return [e for e in self._events if e["seq"] > after_seq]

    def snapshot(self) -> JobSnapshot:
        return JobSnapshot(
            id=self.id,
            type=self.type,
            label=self.label,
            status=self.status,
            progress=self.progress,
            message=self.message,
            result=self.result,
            error=self.error,
        )


class JobManager:
    def __init__(self, max_workers: int = 4):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="job")

    def start(self, type_: str, label: str, fn: Callable[[Job], None]) -> Job:
        job = Job(uuid.uuid4().hex[:12], type_, label)
        with self._lock:
            self._jobs[job.id] = job
        self._executor.submit(self._run, job, fn)
        return job

    def _run(self, job: Job, fn: Callable[[Job], None]) -> None:
        try:
            result = fn(job)
            # 函数返回值（非 None 且尚未自行终结）自动作为任务结果
            if result is not None and job.status == "running":
                job.set_result(result)
        except Exception as exc:  # noqa: BLE001
            job.fail(f"{type(exc).__name__}: {exc}")
        # 保留最近 200 个任务
        with self._lock:
            if len(self._jobs) > 200:
                for old_id in list(self._jobs.keys())[: len(self._jobs) - 200]:
                    if self._jobs[old_id].status != "running":
                        del self._jobs[old_id]

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self, limit: int = 20) -> list[JobSnapshot]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)[:limit]
        return [j.snapshot() for j in jobs]


manager = JobManager()
