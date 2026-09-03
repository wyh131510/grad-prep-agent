#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eval_review.py —— 多智能体评审有效性评测脚本（对应测试用例类 E）

数据准备（tests/proposals/）：
  - proposal_N.md  ：5 篇预埋真实逻辑问题的开题报告初稿（用 ## 标题分节）
  - defects_N.json ：标准答案——每篇 2~3 条预埋问题，每条含 1~3 个命中关键词

流程：对每篇初稿
  1) POST /api/tasks                                    创建调研任务
  2) PUT  /api/tasks/{id}/proposal/sections/{key}       逐节写入初稿内容
  3) POST /api/tasks/{id}/review                        启动多智能体评审（后台 Job）
  4) GET  /api/jobs/{job_id}                            轮询直到 status != running
  5) GET  /api/tasks/{id}/review                        取 merged 与 4 个 results
  6) 把全部 issue 文本与预埋问题关键词（含同义词扩展）比对，
     计算每稿检出率与总体检出率，对照 ≥80% 输出 PASS/FAIL，
     结果写入 tests/output/review_report.json
"""
import argparse
import json
import re
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
PROPOSALS_DIR = SCRIPT_DIR / "proposals"
PASS_RATE = 0.80      # 通过标准：预埋问题总体检出率 ≥ 80%

KEY_HINTS = ("api key", "apikey", "api_key", "provider", "服务商", "密钥", "未配置", "没有配置", "配置")

# 分节标题 → 默认分块 key（与 docs/API.md 的默认分块一致）
SECTION_HEADINGS = {
    "课题背景与研究意义": "background",
    "国内外研究现状": "literature_review",
    "研究内容与目标": "objectives",
    "研究方案与技术路线": "methodology",
    "可行性分析": "feasibility",
    "进度安排": "schedule",
    "参考文献": "references",
}

# 关键词同义词扩展表：评审文本命中关键词或其同义词任一即认为检出该问题
SYNONYMS = {
    "技术路线": ["研究方案", "技术方案", "实施方案", "实现路径", "技术路径", "路线"],
    "研究问题": ["研究目标", "研究内容", "研究点", "问题定义"],
    "工作量": ["进度", "任务量", "时间安排", "进度安排", "工期", "计划"],
    "可行性": ["条件", "资源", "环境", "软硬件", "设备", "算力"],
    "格式": ["模板", "排版", "版式", "规范", "结构"],
    "参考文献": ["引用", "文献标注", "著录", "引文", "文献"],
    "指标": ["评价指标", "评价标准", "验证指标", "评估指标"],
    "数据": ["数据集", "样本", "数据源"],
    "可得": ["获取", "取得", "来源", "可得性", "采集"],
    "匹配": ["一致", "对应", "吻合", "衔接", "相符"],
    "不匹配": ["不一致", "脱节", "矛盾", "不对应", "冲突"],
    "验证": ["实验验证", "试验验证", "检验", "论证"],
    "部署": ["移植", "落地", "端侧", "推理加速", "嵌入式部署"],
    "嵌入式": ["边缘", "端侧", "嵌入式平台", "移动端"],
    "分布式": ["分布", "分散", "分布式控制"],
    "协调": ["协同", "配合", "联合控制"],
    "机理": ["机制", "规律", "演化规律"],
    "预测": ["回归", "拟合", "机器学习模型"],
    "创新点": ["创新", "新颖性", "创新之处"],
    "成熟": ["已成熟", "研究较多", "成果丰富"],
    "试验": ["实验", "试件", "测试"],
}


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


def put_json(base, path, payload):
    """PUT 并解析 JSON；连接失败按 SKIP 处理"""
    try:
        r = requests.put(base + path, json=payload, timeout=60)
    except requests.exceptions.ConnectionError:
        print("[SKIP] 与服务连接中断：请确认服务仍在运行")
        sys.exit(0)
    if r.status_code >= 400:
        check_skip(r, f"PUT {path}")
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


def parse_sections(md_text):
    """按 ## 标题把 Markdown 初稿切分到默认分块 key"""
    sections, cur_key, cur_lines = {}, None, []
    for line in md_text.splitlines():
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            if cur_key:
                sections[cur_key] = "\n".join(cur_lines).strip()
            title = m.group(1).strip()
            cur_key = SECTION_HEADINGS.get(title, title if title in SECTION_HEADINGS.values() else None)
            if cur_key is None:
                print(f"  [WARN] 无法识别的分节标题：{title}（已忽略该节）")
            cur_lines = []
        else:
            cur_lines.append(line)
    if cur_key:
        sections[cur_key] = "\n".join(cur_lines).strip()
    return sections


def expand_candidates(defect):
    """关键词 + 全局同义词表 + 缺陷自带 synonyms 的并集（去重保序）"""
    cands = []
    for kw in defect.get("keywords", []):
        cands.append(kw)
        cands.extend(SYNONYMS.get(kw, []))
        cands.extend((defect.get("synonyms") or {}).get(kw, []))
    return list(dict.fromkeys(cands))


def agent_texts(review):
    """把 4 个评审结果整理为 {agent: 文本}，另加 merged 汇总文本"""
    texts = {}
    for r in review.get("results", []):
        parts = [r.get("agent_name", ""), r.get("summary", "")]
        for issue in r.get("issues", []):
            parts += [issue.get("problem", ""), issue.get("suggestion", ""), issue.get("evidence", "")]
        texts[r.get("agent", "")] = " ".join(parts)
    merged = review.get("merged") or {}
    parts = []
    for c in merged.get("conflicts", []):
        parts += [c.get("topic", ""), " ".join(c.get("opinions", [])), c.get("resolution", "")]
    for s in merged.get("final_suggestions", []):
        parts += [s.get("section", ""), s.get("action", ""), s.get("reason", "")]
    parts += merged.get("strengths", [])
    texts["merged"] = " ".join(parts)
    return texts


def match_defect(defect, texts):
    """缺陷是否被检出：任一候选词出现在任一评审文本中即算命中"""
    cands = expand_candidates(defect)
    full = " ".join(texts.values()).lower()
    for c in cands:
        if c.lower() in full:
            by = [a for a, t in texts.items() if c.lower() in t.lower()]
            return True, c, by
    return False, None, []


def run(base, proposals_dir, timeout):
    """主流程：逐稿写入初稿 → 启动评审 → 取结果 → 关键词比对 → 报告"""
    check_health(base)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    defect_files = sorted(Path(proposals_dir).glob("defects_*.json"))
    if not defect_files:
        print(f"[SKIP] 未在 {proposals_dir} 找到 defects_*.json")
        sys.exit(0)
    per_draft, errors = [], []
    for df in defect_files:
        meta = json.loads(df.read_text(encoding="utf-8"))
        md_path = Path(proposals_dir) / meta.get(
            "proposal", df.name.replace("defects_", "proposal_").replace(".json", ".md"))
        defects = meta.get("defects", [])
        print(f"\n===== {df.name}：{meta.get('major')}｜{meta.get('topic')}（预埋 {len(defects)} 个问题）=====")
        if not md_path.exists():
            print(f"[FAIL] 初稿文件不存在：{md_path}")
            errors.append({"file": df.name, "error": "初稿文件不存在"})
            continue
        md_text = md_path.read_text(encoding="utf-8")
        t = meta.get("task", {})
        try:
            task = post_json(base, "/api/tasks", {
                "topic": t.get("topic", meta.get("topic", "")),
                "major": t.get("major", meta.get("major", "")),
                "year_from": t.get("year_from", 2019), "year_to": t.get("year_to", 2025),
                "sources": t.get("sources") or [],
                "requirements": t.get("requirements", ""),
            })
            task_id = task.get("id")
            print(f"  任务已创建：{task_id}")
            sections = parse_sections(md_text)
            if not sections:
                raise RuntimeError("未解析出任何分节（请确认初稿使用 ## 标题分节）")
            for key, content in sections.items():
                put_json(base, f"/api/tasks/{task_id}/proposal/sections/{key}", {"content": content})
            print(f"  已写入 {len(sections)} 个分块：{'、'.join(sections)}")
            started = post_json(base, f"/api/tasks/{task_id}/review", {})
            job = wait_job(base, started.get("job_id"), timeout, "评审")
            if job.get("status") == "error":
                raise RuntimeError(str(job.get("error")))
            review = get_json(base, f"/api/tasks/{task_id}/review")
            (OUT_DIR / f"review_{task_id}.json").write_text(
                json.dumps({"task_id": task_id, "defects_file": df.name, "review": review},
                           ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  评审完成，原始结果已保存：output/review_{task_id}.json")
        except (RuntimeError, TimeoutError) as e:
            print(f"[FAIL] 该稿评审流程失败：{e}")
            errors.append({"file": df.name, "error": str(e)})
            continue
        texts = agent_texts(review)
        result_defects = []
        for d in defects:
            hit, word, by = match_defect(d, texts)
            result_defects.append({
                "id": d.get("id"), "type": d.get("type"), "problem": d.get("problem"),
                "keywords": d.get("keywords"),
                "detected": hit, "matched_keyword": word, "detected_by": by,
            })
        detected = sum(1 for d in result_defects if d["detected"])
        rate = detected / len(result_defects) if result_defects else None
        scores = {r.get("agent"): r.get("score") for r in review.get("results", [])}
        per_draft.append({
            "file": df.name, "task_id": task_id, "topic": meta.get("topic"),
            "major": meta.get("major"), "defects": result_defects,
            "detected": detected, "total": len(result_defects),
            "rate": round(rate, 4) if rate is not None else None,
            "review_scores": scores,
        })
        for d in result_defects:
            mark = "命中" if d["detected"] else "未命中"
            extra = f"（关键词“{d['matched_keyword']}”，来自 {d['detected_by']}）" if d["detected"] else ""
            print(f"  [{mark}] {d['id']} {d['type']}{extra}")
        print(f"  该稿检出率：{detected}/{len(result_defects)} = {rate:.0%}" if rate is not None else "  该稿无预埋问题")
    total_detected = sum(d["detected"] for d in per_draft)
    total_defects = sum(d["total"] for d in per_draft)
    overall = total_detected / total_defects if total_defects else None
    passed = overall is not None and overall >= PASS_RATE and not errors
    print("\n================ 评审有效性评测报告 ================")
    print(f"通过标准：预埋真实逻辑问题总体检出率 ≥ {PASS_RATE:.0%}（5 稿共 {total_defects} 个预埋问题）")
    for d in per_draft:
        r = f"{d['rate']:.0%}" if d.get("rate") is not None else "N/A"
        print(f"  {d['file']}（{d.get('major')}）：{d['detected']}/{d['total']} = {r}；评审分数：{d.get('review_scores')}")
    if overall is not None:
        print(f"总体检出率：{total_detected}/{total_defects} = {overall:.1%} → {'PASS' if passed else 'FAIL'}")
    else:
        print("总体检出率：无法计算 → FAIL")
    for e in errors:
        print(f"  [流程错误] {e}")
    agent_stats = {}
    for d in per_draft:
        for dd in d["defects"]:
            for a in dd.get("detected_by", []):
                agent_stats[a] = agent_stats.get(a, 0) + 1
    report = {
        "generated_at": now_iso(), "base_url": base,
        "criteria": {"threshold": PASS_RATE, "metric": "预埋真实逻辑问题检出率（评审文本关键词+同义词匹配）"},
        "drafts": per_draft, "errors": errors,
        "total_detected": total_detected, "total_defects": total_defects,
        "overall_rate": overall, "overall_pass": passed,
        "detections_by_agent": agent_stats,
        "note": "检出判定=评审输出文本（4 个角色评审 + 一致性汇总）命中缺陷关键词或同义词；"
                "流程失败（如某角色缺服务商）的初稿按未检出计入，且 overall_pass 判 FAIL",
    }
    report_path = OUT_DIR / "review_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n评测报告已写入：{report_path}")


def main():
    ap = argparse.ArgumentParser(description="多智能体评审有效性评测（用例类 E）")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000", help="后端服务基地址")
    ap.add_argument("--proposals-dir", default=str(PROPOSALS_DIR), help="初稿与标准答案目录（默认 tests/proposals）")
    ap.add_argument("--timeout", type=int, default=600, help="单个评审 Job 轮询超时秒数（默认 600）")
    args = ap.parse_args()
    run(args.base_url, args.proposals_dir, args.timeout)


if __name__ == "__main__":
    main()
