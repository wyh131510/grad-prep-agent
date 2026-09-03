#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eval_summary.py —— 文献摘要质量评测脚本（对应测试用例类 C）

两段式流程：
  第一段（默认）：对给定的 paper_id 列表逐篇
      POST /api/papers/{id}/summarize  生成单篇结构化总结（后台 Job）
      GET  /api/jobs/{job_id}          轮询直到 status != running
      摘要原文保存到 tests/output/summary_{paper_id}.json（供人工评分对照）
      结果导出 tests/output/summary_scores.csv
      （列：编号、标题、得分(1~5)、备注；得分与备注为空列）
  第二段（--annotate-done）：人工按 1~5 分评分并填写备注后重跑，
      汇总平均分，对照 ≥4/5 且无关键信息丢失输出 PASS/FAIL，
      写入 tests/output/summary_report.json

评分维度（详见 tests/test_cases.md TC-C1/TC-C2）：
  1. 关键信息保留：研究问题/方法/贡献/数据/指标/局限是否齐全且与原文一致
  2. 与选题关联性阐述：relevance_to_topic 是否具体、可指导选题
  3. 结构完整性：各字段非空、无乱码、language=zh
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
    print("[SKIP] 缺少依赖 requests，请先安装：pip install requests")
    sys.exit(0)

SCRIPT_DIR = Path(__file__).resolve().parent
OUT_DIR = SCRIPT_DIR / "output"
PASS_AVG = 4.0         # 通过标准：平均分 ≥ 4/5

KEY_HINTS = ("api key", "apikey", "api_key", "provider", "服务商", "密钥", "未配置", "没有配置", "配置")
LOSS_HINTS = ("丢失", "缺失", "遗漏", "漏掉", "缺漏")   # 备注中标注关键信息丢失的提示词


def now_iso():
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
        if line != last_line:
            print(line)
            last_line = line
        if status != "running":
            return job
        time.sleep(3)


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def parse_papers_arg(papers_arg, papers_file):
    """解析 --papers（逗号分隔）或 --papers-file（JSON 数组），返回 [{'id','title'}]"""
    if papers_file:
        p = Path(papers_file)
        if not p.exists():
            print(f"[SKIP] 文件不存在：{p}")
            sys.exit(0)
        raw = json.loads(p.read_text(encoding="utf-8"))
    elif papers_arg:
        raw = [s.strip() for s in papers_arg.split(",") if s.strip()]
    else:
        print("[SKIP] 必须通过 --papers 或 --papers-file 指定 paper_id 列表")
        sys.exit(0)
    out = []
    for x in raw:
        if isinstance(x, dict):
            out.append({"id": x.get("id", ""), "title": x.get("title", "")})
        else:
            out.append({"id": str(x), "title": ""})
    return out


def run(base, papers, timeout):
    """第一段：逐篇生成摘要并导出评分表（得分/备注留空）"""
    check_health(base)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / "summary_scores.csv"
    rows_map = {}
    if csv_path.exists():
        # 保留已有的人工评分：重跑生成流程时不覆盖
        for r in read_csv(csv_path):
            rows_map[r.get("编号", "")] = r
    for i, entry in enumerate(papers, 1):
        pid = entry["id"]
        print(f"\n===== [{i}/{len(papers)}] {pid} =====")
        title = entry.get("title", "")
        try:
            paper = get_json(base, f"/api/papers/{pid}")
            title = paper.get("title") or title
            started = post_json(base, f"/api/papers/{pid}/summarize", {})
            job = wait_job(base, started.get("job_id"), timeout, "摘要")
            if job.get("status") == "error":
                raise RuntimeError(str(job.get("error")))
            summary = job.get("result") or {}
            out_path = OUT_DIR / f"summary_{pid}.json"
            out_path.write_text(json.dumps(
                {"paper_id": pid, "title": title, "summary": summary},
                ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  摘要已生成，参考文件：{out_path}")
            filled = [k for k, v in summary.items() if v]
            print(f"  已填充字段：{'、'.join(filled) if filled else '（无）'}")
            row = {"编号": pid, "标题": title, "得分(1~5)": "", "备注": ""}
        except (RuntimeError, TimeoutError) as e:
            print(f"[FAIL] 摘要生成失败：{e}")
            row = {"编号": pid, "标题": title, "得分(1~5)": "", "备注": f"生成失败：{e}"}
        if pid in rows_map:   # 恢复已有评分，避免重跑丢失人工标注
            row["得分(1~5)"] = rows_map[pid].get("得分(1~5)", "")
            row["备注"] = rows_map[pid].get("备注", "")
        rows_map[pid] = row
    write_csv(csv_path, ["编号", "标题", "得分(1~5)", "备注"], list(rows_map.values()))
    print(f"\n评分表已导出：{csv_path}")
    print("下一步：人工逐篇对照 output/summary_{paper_id}.json 打分（1~5），"
          "备注可用“丢失/缺失/遗漏”标注关键信息丢失，然后加 --annotate-done 重跑")


def annotate():
    """第二段：读取人工评分，汇总平均分并输出 PASS/FAIL"""
    csv_path = OUT_DIR / "summary_scores.csv"
    if not csv_path.exists():
        print("[SKIP] 未找到 summary_scores.csv：请先不带 --annotate-done 跑一遍摘要生成流程")
        sys.exit(0)
    rows = read_csv(csv_path)
    scored, issues = [], []
    for r in rows:
        raw = str(r.get("得分(1~5)", "")).strip()
        note = str(r.get("备注", "")).strip()
        if raw == "":
            issues.append(f"{r.get('编号')} 未评分")
            continue
        try:
            s = float(raw)
        except ValueError:
            issues.append(f"{r.get('编号')} 得分格式非法：{raw}")
            continue
        scored.append({"编号": r.get("编号"), "标题": r.get("标题"), "得分": s, "备注": note})
        if s < 3:
            issues.append(f"{r.get('编号')} 得分 {s} < 3（疑似关键信息丢失）")
        if any(h in note for h in LOSS_HINTS):
            issues.append(f"{r.get('编号')} 备注标注关键信息丢失：{note}")
    avg = round(sum(s["得分"] for s in scored) / len(scored), 2) if scored else None
    passed = (len(rows) > 0 and len(scored) == len(rows) and avg is not None
              and avg >= PASS_AVG and not issues)
    print("\n================ 文献摘要评测报告 ================")
    print(f"通过标准：平均分 ≥ {PASS_AVG}/5，且无关键信息丢失（无 <3 分、备注无丢失标注）")
    for s in scored:
        print(f"  {s['编号']}｜{s['标题'][:40]}：{s['得分']} 分")
    print(f"共 {len(rows)} 篇，已评分 {len(scored)} 篇，平均分：{avg if avg is not None else 'N/A'}")
    for msg in issues:
        print("  [问题]", msg)
    print(f"结论：{'PASS' if passed else 'FAIL'}")
    report = {
        "generated_at": now_iso(),
        "criteria": {"min_average": PASS_AVG, "max_score": 5, "no_key_info_loss": True,
                     "metric": "人工 1~5 分评分均值（维度：关键信息保留/选题关联性/结构完整性）"},
        "papers": scored, "issues": issues,
        "average": avg, "annotated": len(scored), "total": len(rows),
        "overall_pass": passed,
    }
    report_path = OUT_DIR / "summary_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n评测报告已写入：{report_path}")


def main():
    ap = argparse.ArgumentParser(description="文献摘要质量评测（用例类 C）")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000", help="后端服务基地址")
    ap.add_argument("--papers", default=None, help="paper_id 列表，逗号分隔，如 p_xxx,p_yyy")
    ap.add_argument("--papers-file", default=None, help="paper_id 列表 JSON 文件（字符串数组或 [{\"id\":..,\"title\":..}]）")
    ap.add_argument("--timeout", type=int, default=300, help="单个摘要 Job 轮询超时秒数（默认 300）")
    ap.add_argument("--annotate-done", action="store_true", help="人工评分已完成，进入统计与 PASS/FAIL 判定")
    args = ap.parse_args()
    if args.annotate_done:
        annotate()
        return
    run(args.base_url, parse_papers_arg(args.papers, args.papers_file), args.timeout)


if __name__ == "__main__":
    main()
