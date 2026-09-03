#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eval_translation.py —— 英文文献翻译质量评测脚本（对应测试用例类 D）

前置条件：
  - 10 段英文样本见 tests/translation_samples.json（5 个领域各 2 段，含 key_terms 标准译法）
  - 已把样本作为文献导入系统（导入方式见 tests/README.md），得到 10 个 paper_id
  - 将 10 个 paper_id 按样本顺序写入 JSON 数组文件，用 --papers-json 传入

两段式流程：
  第一段（默认）：按索引把 paper 与样本一一配对，逐篇
      POST /api/papers/{id}/translate  标题+摘要翻译（后台 Job）
      GET  /api/jobs/{job_id}          轮询直到 status != running
      译文（title_zh/abstract_zh/glossary）保存到 tests/output/translation_{paper_id}.json
      结果导出 tests/output/translation_scores.csv
      （列：编号、原文标题、术语一致率(%)、信息完整(是/否)、备注；后三列留空）
  第二段（--annotate-done）：人工对照译文与 key_terms 填写术语一致率与信息完整后重跑，
      统计术语一致率均值 ≥95% 且无漏译/错译 → PASS/FAIL，
      写入 tests/output/translation_report.json

术语一致率判定（人工）：统计样本 key_terms 各次出现是否采用标准译法，
  一致次数 / 总出现次数 × 100%；信息完整 = 标题与摘要无漏译、无错译。
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
SAMPLES_PATH = SCRIPT_DIR / "translation_samples.json"
PASS_TERM = 95.0       # 通过标准：术语一致率均值 ≥ 95%
PASS_N_SAMPLES = 10    # 样本规模：10 段

KEY_HINTS = ("api key", "apikey", "api_key", "provider", "服务商", "密钥", "未配置", "没有配置", "配置")


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


def run(base, papers_file, timeout):
    """第一段：逐篇翻译并导出人工检查表（术语一致率/信息完整留空）"""
    check_health(base)
    samples = json.loads(SAMPLES_PATH.read_text(encoding="utf-8"))
    papers = json.loads(Path(papers_file).read_text(encoding="utf-8"))
    ids = [p.get("id") if isinstance(p, dict) else p for p in papers]
    n = min(len(samples), len(ids))
    if len(ids) != PASS_N_SAMPLES or n != PASS_N_SAMPLES:
        print(f"[WARN] 期望 {PASS_N_SAMPLES} 篇文献（对应 10 段样本），实际传入 {len(ids)} 篇，"
              f"将按前 {n} 段样本配对评测")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / "translation_scores.csv"
    rows_map = {}
    if csv_path.exists():
        # 保留已有的人工检查结果：重跑翻译时不覆盖
        for r in read_csv(csv_path):
            rows_map[r.get("编号", "")] = r
    for i in range(n):
        sample = samples[i]
        pid = ids[i]
        print(f"\n===== [{i + 1}/{n}] {sample['id']}（{sample['domain']}）paper={pid} =====")
        print(f"  原文标题：{sample['title']}")
        try:
            started = post_json(base, f"/api/papers/{pid}/translate", {})
            job = wait_job(base, started.get("job_id"), timeout, "翻译")
            if job.get("status") == "error":
                raise RuntimeError(str(job.get("error")))
            result = job.get("result") or {}
            out_path = OUT_DIR / f"translation_{pid}.json"
            out_path.write_text(json.dumps({
                "sample_id": sample["id"], "paper_id": pid, "domain": sample["domain"],
                "title": sample["title"], "abstract": sample["abstract"],
                "key_terms": sample.get("key_terms", []), "translation": result,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  译文标题：{result.get('title_zh', '')}")
            print(f"  术语表：{json.dumps(result.get('glossary', {}), ensure_ascii=False)[:120]}")
            print(f"  参考文件：{out_path}")
            row = {"编号": sample["id"], "原文标题": sample["title"],
                   "术语一致率(%)": "", "信息完整(是/否)": "", "备注": ""}
        except (RuntimeError, TimeoutError) as e:
            print(f"[FAIL] 翻译失败：{e}")
            row = {"编号": sample["id"], "原文标题": sample["title"],
                   "术语一致率(%)": "", "信息完整(是/否)": "", "备注": f"翻译失败：{e}"}
        if sample["id"] in rows_map:   # 恢复已有标注
            old = rows_map[sample["id"]]
            row["术语一致率(%)"] = old.get("术语一致率(%)", "")
            row["信息完整(是/否)"] = old.get("信息完整(是/否)", "")
            row["备注"] = old.get("备注", "")
        rows_map[sample["id"]] = row
    write_csv(csv_path, ["编号", "原文标题", "术语一致率(%)", "信息完整(是/否)", "备注"],
              [rows_map[s["id"]] for s in samples[:n]])
    print(f"\n检查表已导出：{csv_path}")
    print("下一步：人工对照 output/translation_{paper_id}.json 中译文与 key_terms 标准译法，")
    print("填写术语一致率(%)（0-100）与信息完整(是/否)，然后加 --annotate-done 重跑")


def annotate():
    """第二段：读取人工检查结果，统计术语一致率均值并输出 PASS/FAIL"""
    csv_path = OUT_DIR / "translation_scores.csv"
    if not csv_path.exists():
        print("[SKIP] 未找到 translation_scores.csv：请先不带 --annotate-done 跑一遍翻译流程")
        sys.exit(0)
    rows = read_csv(csv_path)
    scores, problems = [], []
    for r in rows:
        raw = str(r.get("术语一致率(%)", "")).strip().replace("%", "")
        complete = str(r.get("信息完整(是/否)", "")).strip()
        if raw == "" or complete == "":
            problems.append(f"{r.get('编号')} 未完成标注（术语一致率或信息完整为空）")
            continue
        try:
            score = float(raw)
        except ValueError:
            problems.append(f"{r.get('编号')} 术语一致率非法：{raw}")
            continue
        scores.append({"编号": r.get("编号"), "原文标题": r.get("原文标题"),
                       "术语一致率": score, "信息完整": complete, "备注": r.get("备注", "")})
        if complete == "否":
            problems.append(f"{r.get('编号')} 信息完整=否（存在漏译/错译）")
    avg = round(sum(s["术语一致率"] for s in scores) / len(scores), 2) if scores else None
    passed = (len(rows) > 0 and len(scores) == len(rows) and avg is not None
              and avg >= PASS_TERM and not problems)
    print("\n================ 翻译质量评测报告 ================")
    print(f"通过标准：术语一致率均值 ≥ {PASS_TERM}%，且全部样本信息完整（无漏译/错译）")
    for s in scores:
        print(f"  {s['编号']}｜{s['原文标题'][:40]}：术语一致率 {s['术语一致率']}%，信息完整 {s['信息完整']}")
    print(f"术语一致率均值：{avg if avg is not None else 'N/A'}%")
    for msg in problems:
        print("  [问题]", msg)
    print(f"结论：{'PASS' if passed else 'FAIL'}")
    report = {
        "generated_at": now_iso(),
        "criteria": {"min_avg_term_consistency": PASS_TERM, "no_missing_or_wrong_translation": True,
                     "metric": "术语一致率均值（对照 key_terms 标准译法）+ 信息完整度（无漏译/错译）"},
        "samples": scores, "problems": problems,
        "avg_term_consistency": avg, "overall_pass": passed,
    }
    report_path = OUT_DIR / "translation_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n评测报告已写入：{report_path}")


def main():
    ap = argparse.ArgumentParser(description="翻译质量评测（用例类 D）")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000", help="后端服务基地址")
    ap.add_argument("--papers-json", required=True,
                    help="10 篇已入库英文文献的 paper_id 列表 JSON 文件（与 translation_samples.json 样本顺序一一对应）")
    ap.add_argument("--timeout", type=int, default=300, help="单个翻译 Job 轮询超时秒数（默认 300）")
    ap.add_argument("--annotate-done", action="store_true", help="人工检查已完成，进入统计与 PASS/FAIL 判定")
    args = ap.parse_args()
    if args.annotate_done:
        annotate()
        return
    if not Path(args.papers_json).exists():
        print(f"[SKIP] 文献列表文件不存在：{args.papers_json}")
        print("[SKIP] 请先把 tests/translation_samples.json 的 10 段样本导入文献库，"
              "再按样本顺序把 10 个 paper_id 写入 JSON 数组文件（见 tests/README.md）")
        sys.exit(0)
    run(args.base_url, args.papers_json, args.timeout)


if __name__ == "__main__":
    main()
