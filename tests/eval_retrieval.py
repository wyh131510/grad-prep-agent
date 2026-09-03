#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eval_retrieval.py —— 检索召回质量评测脚本（对应测试用例类 A）

两段式流程：
  第一段（默认）：对每个选题依次执行
      POST /api/tasks                创建调研任务
      POST /api/tasks/{id}/search    启动检索（后台 Job）
      GET  /api/jobs/{job_id}        轮询直到 status != running
      GET  /api/tasks/{id}/papers?sort=score&limit=K   导出 top-k
      写入 tests/output/retrieval_{task_id}.csv，relevant 列为空
  第二段（--annotate-done）：人工在 CSV 的 relevant 列填 1(相关)/0(不相关) 后重跑，
      统计每个选题 top-k 相关比例、5 个选题（前 5 个 = 每专业第 1 个）平均比例，
      对照 ≥70% 输出 PASS/FAIL，写入 tests/output/retrieval_report.json

退出约定：
  - 前置条件缺失（服务未启动 / 未配置 API Key 等）→ 打印 SKIP 原因并 exit 0
  - 正常跑完（含 FAIL 结论）→ exit 0；参数错误 → argparse exit 2
"""
import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    # 可选依赖缺失：打印提示后优雅退出
    print("[SKIP] 缺少依赖 requests，请先安装：pip install requests")
    sys.exit(0)

SCRIPT_DIR = Path(__file__).resolve().parent
OUT_DIR = SCRIPT_DIR / "output"
DEFAULT_TOPICS = SCRIPT_DIR / "sample_topics.json"
TOP_K_DEFAULT = 10
THRESHOLD = 0.70        # 通过标准：top-k 相关比例 ≥ 70%
PRIMARY_COUNT = 5       # 官方口径：前 5 个选题（5 个专业各 1 个）的平均比例

# 判定“未配置 API Key/服务商”的提示词（接口返回 detail 命中则按 SKIP 处理）
KEY_HINTS = ("api key", "apikey", "api_key", "provider", "服务商", "密钥", "未配置", "没有配置", "配置")


def now_iso():
    """当前时间 ISO 字符串"""
    return datetime.now().isoformat(timespec="seconds")


def check_health(base):
    """前置检查：服务是否可达；不可达时打印原因并 SKIP 退出"""
    try:
        r = requests.get(base + "/api/health", timeout=10)
    except requests.exceptions.ConnectionError:
        print("[SKIP] 无法连接服务（连接被拒绝）：请先启动后端，例如在项目根目录执行 python run.py")
        print(f"[SKIP] 当前 --base-url = {base}")
        sys.exit(0)
    if r.status_code != 200:
        print(f"[SKIP] GET /api/health 返回 HTTP {r.status_code}，服务可能未就绪")
        sys.exit(0)
    h = r.json()
    print(f"[OK] 服务健康：status={h.get('status')} version={h.get('version')} optional={h.get('optional')}")


def check_skip(r, action):
    """接口返回 4xx/5xx：若疑似未配置 API Key/服务商则 SKIP 退出，否则抛异常"""
    try:
        detail = r.json().get("detail", "")
    except Exception:
        detail = r.text
    detail = str(detail)
    if any(h in detail.lower() for h in KEY_HINTS):
        print(f"[SKIP] {action} 返回错误，疑似未配置 API Key/服务商：{detail}")
        print("[SKIP] 请先在设置页配置服务商 API Key 后重跑")
        sys.exit(0)
    raise RuntimeError(f"{action} 失败：HTTP {r.status_code} {detail}")


def get_json(base, path):
    """GET 并解析 JSON；连接失败按 SKIP 处理"""
    try:
        r = requests.get(base + path, timeout=30)
    except requests.exceptions.ConnectionError:
        print("[SKIP] 与服务连接中断：请确认服务仍在运行")
        sys.exit(0)
    if r.status_code >= 400:
        check_skip(r, f"GET {path}")
    return r.json()


def post_json(base, path, payload=None):
    """POST 并解析 JSON；连接失败按 SKIP 处理"""
    try:
        r = requests.post(base + path, json=payload or {}, timeout=60)
    except requests.exceptions.ConnectionError:
        print("[SKIP] 与服务连接中断：请确认服务仍在运行")
        sys.exit(0)
    if r.status_code >= 400:
        check_skip(r, f"POST {path}")
    return r.json()


def wait_job(base, job_id, timeout, label):
    """轮询 Job 快照直到 status != running；返回最终 Job"""
    deadline = time.time() + timeout
    last_line = ""
    while True:
        if time.time() > deadline:
            raise TimeoutError(f"{label} 超时（>{timeout}s），请加大 --timeout 或检查服务日志")
        job = get_json(base, f"/api/jobs/{job_id}")
        status = job.get("status")
        line = f"  [{label}] {status} {int((job.get('progress') or 0) * 100)}% {job.get('message') or ''}"
        if line != last_line:          # 只在进度变化时打印，避免刷屏
            print(line)
            last_line = line
        if status != "running":
            return job
        time.sleep(3)


def read_csv(path):
    """读取 CSV（兼容 utf-8-sig）"""
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path, header, rows):
    """写 CSV，带 BOM 便于 Excel 直接打开"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def run(base, topics, top_k, timeout):
    """第一段：创建任务 → 检索 → 导出 top-k CSV（relevant 列留空供人工标注）"""
    check_health(base)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    meta_path = OUT_DIR / "retrieval_tasks.json"
    tasks_meta = []
    for idx, t in enumerate(topics):
        print(f"\n===== [{idx + 1}/{len(topics)}] {t.get('major')}：{t.get('topic')} =====")
        try:
            task = post_json(base, "/api/tasks", {
                "topic": t["topic"], "major": t["major"],
                "year_from": t["year_from"], "year_to": t["year_to"],
                "sources": t.get("sources") or [],
                "requirements": t.get("requirements", ""),
            })
        except RuntimeError as e:
            print(f"[FAIL] 创建任务失败：{e}")
            continue
        task_id = task.get("id")
        print(f"  任务已创建：{task_id}")
        try:
            started = post_json(base, f"/api/tasks/{task_id}/search", {})
            job = wait_job(base, started.get("job_id"), timeout, "检索")
        except (RuntimeError, TimeoutError) as e:
            print(f"[FAIL] 检索失败：{e}")
            continue
        if job.get("status") == "error":
            print(f"[FAIL] 检索任务出错：{job.get('error')}")
            continue
        result = job.get("result") or {}
        sub_q = len((result.get("plan") or {}).get("sub_questions", []))
        print(f"  检索完成：共 {result.get('papers', 0)} 篇文献，拆解子问题 {sub_q} 个")
        try:
            data = get_json(base, f"/api/tasks/{task_id}/papers?sort=score&limit={top_k}")
        except RuntimeError as e:
            print(f"[FAIL] 导出文献失败：{e}")
            continue
        items = data.get("items") or []
        if not items:
            print("[FAIL] top-k 为空（items 为空），请检查检索是否命中文献")
        rows = []
        for i, p in enumerate(items, 1):
            abstract = " ".join((p.get("abstract") or "").split())[:300]   # 摘要前 300 字
            rows.append([i, p.get("title", ""), p.get("year", ""), p.get("source", ""),
                         p.get("url", ""), abstract, ""])                   # relevant 留空
        csv_path = OUT_DIR / f"retrieval_{task_id}.csv"
        write_csv(csv_path, ["编号", "标题", "年份", "来源", "url", "摘要前300字", "relevant"], rows)
        print(f"  top-{min(top_k, len(items))} 已导出：{csv_path}")
        print("  → 请人工打开该 CSV，在 relevant 列填 1（相关）/ 0（不相关）")
        print("  → 相关判定：标题+摘要是否直接针对选题的核心研究问题")
        tasks_meta.append({"topic_index": idx, "task_id": task_id, "topic": t.get("topic"),
                           "major": t.get("major"), "csv": csv_path.name,
                           "top_k": top_k, "exported": len(items)})
    meta_path.write_text(json.dumps(
        {"base_url": base, "top_k": top_k, "threshold": THRESHOLD,
         "created_at": now_iso(), "tasks": tasks_meta},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n任务元数据已写入：{meta_path}")
    if not tasks_meta:
        print("[FAIL] 没有任何选题成功导出文献，无法进入标注阶段")
    else:
        print("\n下一步：人工标注各 CSV 的 relevant 列后，加 --annotate-done 重跑本脚本")


def annotate(base_url, meta_path):
    """第二段：读取人工标注结果，统计各选题比例与前 5 个选题平均，输出 PASS/FAIL"""
    if not meta_path.exists():
        print("[SKIP] 未找到 retrieval_tasks.json：请先不带 --annotate-done 跑一遍检索导出流程")
        sys.exit(0)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    tasks = meta.get("tasks", [])
    print(f"读取任务元数据：{meta_path}（共 {len(tasks)} 个选题）")
    for t in tasks:
        rows = read_csv(OUT_DIR / t["csv"])
        annotated = [r for r in rows if str(r.get("relevant", "")).strip() in ("0", "1")]
        relevant = sum(1 for r in annotated if str(r["relevant"]).strip() == "1")
        ratio = relevant / len(annotated) if annotated else None
        t["annotated"] = len(annotated)
        t["relevant"] = relevant
        t["ratio"] = round(ratio, 4) if ratio is not None else None
        t["pass"] = (t["ratio"] is not None) and (t["ratio"] >= THRESHOLD)
        if not annotated:
            print(f"  [WARN] {t.get('topic')}（{t.get('csv')}）尚未标注 relevant，跳过统计")
    # 官方口径：前 5 个选题（每专业第 1 个）的平均比例；只跑了对照选题时退化为全部已标注选题
    primary = [t for t in tasks if t.get("topic_index", 99) < PRIMARY_COUNT and t.get("ratio") is not None]
    if not primary:
        primary = [t for t in tasks if t.get("ratio") is not None]
    avg = round(sum(t["ratio"] for t in primary) / len(primary), 4) if primary else None
    overall_pass = avg is not None and avg >= THRESHOLD
    print("\n================ 检索召回评测报告 ================")
    print(f"通过标准：top-k 相关比例 ≥ {THRESHOLD:.0%}（按 {PRIMARY_COUNT} 个专业选题的平均比例判定）")
    for t in tasks:
        ratio = f"{t['ratio']:.1%}" if t.get("ratio") is not None else "未标注"
        mark = "PASS" if t.get("pass") else ("FAIL" if t.get("ratio") is not None else "待标注")
        print(f"  [{mark}] {t.get('major')}｜{t.get('topic')}：相关 {t.get('relevant', 0)}/{t.get('annotated', 0)} = {ratio}")
    if avg is not None:
        print(f"5 个专业选题平均相关比例：{avg:.1%} → {'PASS' if overall_pass else 'FAIL'}")
    else:
        print("5 个专业选题平均相关比例：无法计算（标注不完整）→ FAIL")
    report = {
        "generated_at": now_iso(), "base_url": base_url, "top_k": meta.get("top_k"),
        "criteria": {"threshold": THRESHOLD, "primary_topics": PRIMARY_COUNT,
                     "metric": "top-k 相关比例（人工标注 relevant=1 占比）"},
        "tasks": tasks, "primary_average_ratio": avg, "overall_pass": overall_pass,
        "note": "primary_average_ratio 为前 5 个选题（topic_index<5，即每专业第 1 个）的平均比例；"
                "只运行部分选题时按实际已标注范围统计",
    }
    report_path = OUT_DIR / "retrieval_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n评测报告已写入：{report_path}")


def main():
    ap = argparse.ArgumentParser(description="检索召回质量评测（用例类 A）")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000", help="后端服务基地址")
    ap.add_argument("--topics", default=str(DEFAULT_TOPICS), help="选题 JSON 文件路径（默认 tests/sample_topics.json）")
    ap.add_argument("--topic-index", type=int, default=None, help="只跑第 i 个选题（从 0 开始）")
    ap.add_argument("--top-k", type=int, default=TOP_K_DEFAULT, help="导出 top-k 篇（默认 10）")
    ap.add_argument("--timeout", type=int, default=900, help="单个检索 Job 轮询超时秒数（默认 900）")
    ap.add_argument("--annotate-done", action="store_true", help="人工标注已完成，进入统计与 PASS/FAIL 判定")
    args = ap.parse_args()

    if args.annotate_done:
        annotate(args.base_url, OUT_DIR / "retrieval_tasks.json")
        return
    topics_path = Path(args.topics)
    if not topics_path.exists():
        print(f"[SKIP] 选题文件不存在：{topics_path}")
        sys.exit(0)
    topics = json.loads(topics_path.read_text(encoding="utf-8"))
    if args.topic_index is not None:
        if not (0 <= args.topic_index < len(topics)):
            print(f"[SKIP] --topic-index {args.topic_index} 越界：文件共 {len(topics)} 个选题（下标 0~{len(topics) - 1}）")
            sys.exit(0)
        topics = [topics[args.topic_index]]
    run(args.base_url, topics, args.top_k, args.timeout)


if __name__ == "__main__":
    main()
