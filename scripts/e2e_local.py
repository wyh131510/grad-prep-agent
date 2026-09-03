# -*- coding: utf-8 -*-
"""本地端到端自测：需要先启动服务（python run.py），不依赖大模型 API 与外网。

用法：.venv\\Scripts\\python.exe scripts\\e2e_local.py [--base-url http://127.0.0.1:8000]
"""
from __future__ import annotations

import argparse
import sys
import time

import requests

RESULTS: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((bool(cond), name, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail and not cond else ""))


def wait_job(base: str, job_id: str, timeout: int = 120) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(f"{base}/api/jobs/{job_id}", timeout=10)
        job = r.json()
        if job["status"] != "running":
            return job
        time.sleep(0.5)
    return {"status": "timeout", "error": "polling timeout"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")

    # 0. 服务在线
    try:
        r = requests.get(f"{base}/api/health", timeout=5)
        check("GET /api/health", r.status_code == 200 and r.json().get("status") == "ok", str(r.text[:120]))
    except requests.RequestException as exc:
        print(f"[FAIL] 服务未启动：{exc}")
        return 1

    # 1. 概览统计
    r = requests.get(f"{base}/api/stats", timeout=10)
    s = r.json()
    check("GET /api/stats 字段", all(k in s for k in ("tasks", "papers", "collected", "proposals", "reviews")), str(s))

    # 2. 设置
    r = requests.get(f"{base}/api/settings", timeout=10)
    st = r.json()
    check("GET /api/settings 服务商预设", len(st.get("providers", [])) >= 5)
    r = requests.get(f"{base}/api/settings/presets", timeout=10)
    check("GET /api/settings/presets", len(r.json()) >= 5)
    # 检索超时调小（沙箱无外网，避免长等待）
    r = requests.put(f"{base}/api/settings", json={"search_options": {"request_timeout": 3}}, timeout=10)
    check("PUT /api/settings", r.status_code == 200 and r.json()["search_options"]["request_timeout"] == 3)

    # 3. 创建任务
    r = requests.post(
        f"{base}/api/tasks",
        json={
            "topic": "基于YOLOv8的路面裂缝检测方法研究",
            "major": "计算机科学与技术",
            "year_from": 2019,
            "year_to": 2025,
            "sources": ["arxiv"],
            "requirements": "轻量化",
        },
        timeout=10,
    )
    check("POST /api/tasks 创建任务", r.status_code == 200, str(r.text[:200]))
    task = r.json()
    check("POST /api/tasks 返回字段", task.get("id", "").startswith("t_") and task.get("topic"))

    # 4. 导入 EndNote/RIS
    ENDNOTE = """%0 Journal Article
%A Qin Zou
%A Zhang Zhang
%T DeepCrack: Learning Hierarchical Convolutional Features for Crack Detection
%J IEEE Transactions on Image Processing
%D 2019
%K crack detection; deep learning
%X Automatic crack detection from images is a promising technique.
%ER
"""
    RIS = """TY  - JOUR
AU  - Liang-Chieh Chen
TI  - DeepLab: Semantic Image Segmentation with Deep Convolutional Nets
JO  - IEEE TPAMI
PY  - 2018
AB  - In this work we address semantic segmentation.
ER  -"""
    r = requests.post(
        f"{base}/api/tasks/{task['id']}/import",
        files={"file": ("demo.txt", (ENDNOTE + "\n" + RIS).encode("utf-8"), "text/plain")},
        timeout=30,
    )
    check("POST /api/tasks/{id}/import", r.status_code == 200, str(r.text[:200]))
    job = wait_job(base, r.json()["job_id"])
    check("导入 Job 完成", job["status"] == "done" and job["result"].get("imported") == 2, str(job)[:200])

    # 5. 文献列表（任务内 + 全局）
    r = requests.get(f"{base}/api/tasks/{task['id']}/papers", timeout=10).json()
    check("GET /api/tasks/{id}/papers", r["total"] == 2 and len(r["items"]) == 2)
    r2 = requests.get(f"{base}/api/papers", timeout=10).json()
    check("GET /api/papers 全局列表", r2["total"] >= 2)
    paper_id = r["items"][0]["id"]

    # 6. 收藏（不下载）
    r = requests.post(f"{base}/api/papers/{paper_id}/collect", json={"download": False}, timeout=30)
    job = wait_job(base, r.json()["job_id"])
    check("POST /api/papers/{id}/collect", job["status"] == "done" and job["result"].get("collected") == 1, str(job)[:150])
    # 收藏状态已落库 + 新下载状态字段存在
    r = requests.get(f"{base}/api/papers/{paper_id}", timeout=10).json()
    check("收藏状态已落库", r["collected"] is True)
    check("download_status 字段存在", r.get("download_status") in ("none", "downloading", "done", "failed"), str(r.get("download_status")))
    # 取消收藏
    r = requests.delete(f"{base}/api/papers/{paper_id}/collect", timeout=10)
    check("DELETE /api/papers/{id}/collect", r.status_code == 200 and r.json().get("ok") is True)

    # 按需解析全文（导入文献无 PDF/来源页 → 优雅返回 done/no_content）
    r = requests.post(f"{base}/api/papers/{paper_id}/parse_fulltext", timeout=10)
    job = wait_job(base, r.json()["job_id"])
    check("POST /api/papers/{id}/parse_fulltext", job["status"] == "done", str(job.get("error", ""))[:150])

    # 7. 检索流水线（有网络时抓取真实文献；无网络时来源失败被优雅记录，均不崩溃）
    r = requests.post(f"{base}/api/tasks/{task['id']}/search", json={"feedback": ""}, timeout=10)
    job = wait_job(base, r.json()["job_id"], timeout=180)
    check("POST /api/tasks/{id}/search 流水线完成", job["status"] == "done", str(job.get("error", ""))[:200])
    res = job.get("result") or {}
    # 外部检索接口结果不稳定（限流/空结果属正常），此处仅验证流水线健壮完成
    if res.get("sources_ok"):
        r = requests.get(f"{base}/api/tasks/{task['id']}/papers?limit=20", timeout=10).json()
        check("真实网络下抓取到文献（BM25 排序 ≤20 篇）", 0 < len(r["items"]) <= 21, str(r["total"]))
    r = requests.get(f"{base}/api/tasks/{task['id']}", timeout=10).json()
    check("任务状态 searched", r["status"] == "searched" and r["plan"] is not None)
    r = requests.get(f"{base}/api/tasks/{task['id']}/plan", timeout=10)
    check("GET /api/tasks/{id}/plan", r.status_code == 200 and r.json().get("sub_questions"))

    # 8. 开题报告分块
    r = requests.get(f"{base}/api/tasks/{task['id']}/proposal", timeout=10).json()
    check("GET /api/tasks/{id}/proposal 7 分块", len(r["sections"]) == 7 and r["sections"][0]["key"] == "background")
    r = requests.put(
        f"{base}/api/tasks/{task['id']}/proposal/sections/background",
        json={"content": "## 课题背景与研究意义\n\nE2E 测试内容。"},
        timeout=10,
    )
    check("PUT 分块保存", r.status_code == 200 and r.json().get("status") == "edited")
    r = requests.get(f"{base}/api/tasks/{task['id']}/proposal/export", params={"format": "md"}, timeout=10)
    check("GET proposal/export md", r.status_code == 200 and "E2E 测试内容" in r.text)

    # 9. 评审前置校验：无内容 → 明确报错（Job error 而非崩溃）
    r = requests.post(f"{base}/api/tasks/{task['id']}/review", timeout=10)
    job = wait_job(base, r.json()["job_id"])
    check("评审 Job 明确失败而非崩溃", job["status"] == "error" and "内容过少" in (job.get("error") or ""), str(job.get("error", ""))[:120])

    # 10. 未生成答辩清单 → 404
    r = requests.get(f"{base}/api/tasks/{task['id']}/defense", timeout=10)
    check("GET defense 未生成时 404", r.status_code == 404)

    # 11. 服务商连通性测试（沙箱无外网 → 返回失败原因而非异常）
    r = requests.post(
        f"{base}/api/settings/providers/deepseek/test",
        json={"api_key": "sk-fake-for-test"},
        timeout=60,
    )
    body = r.json()
    check("服务商测试接口可用", r.status_code == 200 and "ok" in body and isinstance(body.get("message"), str), str(body)[:120])

    # 12. SSE 事件流（已完成任务）
    job_id = wait_job(base, requests.get(f"{base}/api/jobs", timeout=10).json()[0]["id"]) and r is not None
    r = requests.get(f"{base}/api/jobs", timeout=10).json()
    with requests.get(f"{base}/api/jobs/{r[0]['id']}/events", stream=True, timeout=20) as resp:
        lines = [ln.decode("utf-8", errors="replace") for ln in resp.iter_lines() if ln]
    check("SSE 事件流可读", len(lines) >= 1 and any("event:" in ln for ln in lines), str(lines[:3]))

    # 汇总
    fails = [x for x in RESULTS if not x[0]]
    print("\n" + "=" * 60)
    print(f"端到端检查 {len(RESULTS)} 项：通过 {len(RESULTS) - len(fails)}，失败 {len(fails)}")
    for f in fails:
        print("  FAIL:", f[1], f[2])
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
