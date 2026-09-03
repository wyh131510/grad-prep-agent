# -*- coding: utf-8 -*-
"""离线冒烟测试：验证核心模块逻辑与「无 LLM / 无网络 / 无可选依赖」时的降级路径。

运行：.venv\\Scripts\\python.exe scripts\\smoke_test.py
不依赖 FastAPI（本机沙箱无外网无法安装）与任何网络访问。
"""
from __future__ import annotations

import os
import shutil
import sys
import time

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)

# 使用独立的测试数据目录
TEST_DATA = os.path.join(PROJECT, "data", "smoke_test")
shutil.rmtree(TEST_DATA, ignore_errors=True)
os.makedirs(TEST_DATA, exist_ok=True)
os.environ["GRAD_PREP_DATA_DIR"] = TEST_DATA

RESULTS: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((bool(cond), name, detail))
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f"  ({detail})" if detail and not cond else ""))


# ---------------------------------------------------------------- 0. utils
from app.utils import (  # noqa: E402
    chunk_text, clean_text, make_id, make_soup, parse_json_lenient, parse_year, rrf_fuse, safe_filename,
)

check("clean_text", clean_text("  a\r\n\r\n  b ") == "a\n\nb")
check("parse_json_lenient(代码块+尾逗号)", parse_json_lenient('```json\n{"a": [1,2,],}\n```') == {"a": [1, 2]})
check("parse_json_lenient(截断JSON)", parse_json_lenient('前缀 {"a": {"b": 1}} 后缀') == {"a": {"b": 1}})
check("chunk_text", len(chunk_text("段一。" * 500 + "\n\n" + "段二。" * 500, max_chars=300)) >= 2)
check("rrf_fuse", rrf_fuse([["a", "b"], ["b", "a"]])["b"] > 0)
check("make_id 稳定", make_id("x", "y") == make_id("x", "y"))
check("safe_filename", safe_filename('a/b\\c:d*e?"f<g>h|i.pdf') == "a_b_c_d_e_f_g_h_i.pdf")
check("parse_year", parse_year("2023-05") == 2023 and parse_year("abc") is None)
check("make_soup(降级html.parser)", make_soup("<p>你好</p>").get_text().strip() == "你好")

# ---------------------------------------------------------------- 1. 配置
from app.config import get_settings, save_settings  # noqa: E402

s = get_settings()
check("默认服务商预设", len(s.providers) == 6 and all(not p.api_key for p in s.providers))
s.download_dir = os.path.join(TEST_DATA, "files")
save_settings(s)
check("设置持久化", get_settings().download_dir == s.download_dir)

# ---------------------------------------------------------------- 2. 任务/文献仓库
from app.schemas import TaskCreate  # noqa: E402
from app.store import repo  # noqa: E402

task = repo.create_task(
    TaskCreate(
        topic="基于YOLOv8的路面裂缝检测方法研究",
        major="计算机科学与技术",
        year_from=2019,
        year_to=2025,
        sources=["arxiv"],
        requirements="轻量化",
    )
)
check("创建任务", task.id.startswith("t_"))
check("读取任务", repo.get_task(task.id).topic == task.topic)
check("任务列表", any(t.id == task.id for t in repo.list_tasks()))

# ---------------------------------------------------------------- 3. 文献导入（EndNote/RIS）→ 解析 → 入库
from app.parse.importers import parse_import_text  # noqa: E402
from app.search.engine import import_documents  # noqa: E402
from app.jobs import Job  # noqa: E402

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
JO  - IEEE Transactions on Pattern Analysis and Machine Intelligence
PY  - 2018
AB  - In this work we address semantic segmentation.
ER  -"""

records = parse_import_text(ENDNOTE + "\n" + RIS)
check("解析 EndNote+RIS", len(records) == 2 and records[0]["title"].startswith("DeepCrack"))
check("字段提取", records[0]["year"] == 2019 and len(records[0]["authors"]) == 2 and records[0]["venue"].startswith("IEEE"))

job = Job("smoke-import", "test", "导入")
import_result = import_documents(task, "test.txt", (ENDNOTE + "\n" + RIS).encode("utf-8"), job)
check("导入返回数量", import_result.get("imported") == 2, str(import_result))
total, papers = repo.list_papers(task.id)
check("文献入库", total == 2 and papers[0].source == "import")
p = papers[0]
check("文献字段完整", bool(p.title and p.authors and p.year), p.model_dump_json()[:200])

# ---------------------------------------------------------------- 4. 三重混合检索（离线降级：BM25 内置实现）
from app.retrieve import bm25 as bm25_mod  # noqa: E402
from app.retrieve.hybrid import hybrid_rank  # noqa: E402

check(
    "BM25 实现就绪（rank_bm25 或内置降级）",
    bm25_mod.BM25Okapi is not None or hasattr(bm25_mod, "_MiniBM25"),
)
scores = hybrid_rank(task.topic, ["路面裂缝检测", "crack detection", task.topic], papers)
check("混合检索出分", len(scores) == 2 and sum(1 for v in scores.values() if v[0] > 0) >= 1, str(scores))
check(
    "BM25 有命中、向量/精排降级为0",
    sum(1 for v in scores.values() if v[1] > 0) >= 1 and all(v[2] == 0 and v[3] == 0 for v in scores.values()),
    str(scores),
)

# ---------------------------------------------------------------- 4.5 PubMed 页面图表提取（离线模拟解析）
from app.parse.page_figures import _collect_candidates  # noqa: E402

MOCK_PUBMED_HTML = """
<html><body>
  <div class="figure-item">
    <img class="figure-image-link" src="https://cdn.ncbi.nlm.nih.gov/pmc/blobs/1272/60952258/fig1.png" alt="">
    <div class="figure-caption">Figure 1 Greenhouse elevated strawberry.</div>
  </div>
  <div class="figure-item">
    <img src="https://cdn.ncbi.nlm.nih.gov/pmc/blobs/1272/60952258/fig2.png">
    <div class="figure-caption">Figure 2 Images of strawberries in different ripeness stages</div>
  </div>
  <img src="https://cdn.ncbi.nlm.nih.gov/pmc/blobs/1272/60952258/fig3.png">
  <header><img src="/static/img/logo.svg" alt="logo"></header>
</body></html>
"""
_cands = _collect_candidates(MOCK_PUBMED_HTML)
check(
    "PubMed 模拟页图表候选提取（含图注/无图注/过滤logo）",
    len(_cands) == 3
    and _cands[0][1].startswith("Figure 1")
    and _cands[1][0].endswith("fig2.png")
    and not any("logo" in s for s, _ in _cands),
    str(_cands)[:200],
)

# ---------------------------------------------------------------- 5. 选题拆解（LLM 未配置 → 规则降级）
from app.search.planner import plan_topic  # noqa: E402

plan = plan_topic(task.topic, task.major, "2019~2025", "", job=job)
check("规则降级计划可用", len(plan.sub_questions) >= 1 and plan.sub_questions[0].queries)

# ---------------------------------------------------------------- 6. 检索流水线（网络全断 → 来源失败被优雅记录）
from app.search.engine import run_search_pipeline  # noqa: E402

s = get_settings()
s.search_options.request_timeout = 3
save_settings(s)

job2 = Job("smoke-search", "test", "检索")
result = run_search_pipeline(task, "", job2)
job2.set_result(result)
check("流水线完成（不崩溃）", job2.status == "done", job2.error or "")
check(
    "检索来源正常返回或失败被记录",
    len(result.get("sources_ok", [])) >= 1 or len(result.get("sources_failed", {})) >= 1,
    f"ok={result.get('sources_ok')} failed={result.get('sources_failed')}",
)
check("任务状态→searched", repo.get_task(task.id).status == "searched")
check("检索计划已保存", repo.get_task(task.id).plan is not None)

# ---------------------------------------------------------------- 7. 开题报告分块
from app.agents.proposal import export_markdown, get_sections  # noqa: E402

secs = get_sections(task.id)
check("默认 7 个分块", len(secs) == 7 and secs[0].key == "background")
repo.put_section(task.id, "background", secs[0].title, "## 课题背景与研究意义\n\n这是测试内容。", "draft")
md = export_markdown(repo.get_task(task.id))
check("导出 Markdown", "测试内容" in md and "# " in md)

# ---------------------------------------------------------------- 8. 评审/答辩的边界行为（未生成 → 明确报错而非崩溃）
from app.agents.review import run_review  # noqa: E402

try:
    run_review(repo.get_task(task.id))
    check("空报告评审被拒绝", False)
except ValueError as exc:
    check("空报告评审被拒绝", "内容过少" in str(exc))

# ---------------------------------------------------------------- 9. Job 管理
from app.jobs import manager  # noqa: E402

# 返回值自动成为 Job 结果（manager.start 包装）
j2 = manager.start("smoke-done", "测试", lambda jj: {"ok": 42})
for _ in range(50):
    if j2.status != "running":
        break
    time.sleep(0.1)
check("Job 返回值自动成为 result", j2.status == "done" and j2.result == {"ok": 42}, f"{j2.status} {j2.result}")

j = manager.start("smoke", "测试", lambda jj: jj.fail("boom"))
time.sleep(0.3)
check("Job 失败路径", j.status == "error" and j.error == "boom")
snap = j.snapshot()
check("Job 快照", snap.status == "error" and snap.progress == 0.0)

# ---------------------------------------------------------------- 10. LLM 客户端降级行为
from app.config import PROVIDER_PRESETS  # noqa: E402
from app.llm.client import LLMError, llm  # noqa: E402

try:
    llm.chat(role="planner", messages=[{"role": "user", "content": "hi"}])
    check("未配置 LLM 时明确报错", False)
except LLMError as exc:
    check("未配置 LLM 时明确报错", "设置" in str(exc))
ok, msg = llm.test(PROVIDER_PRESETS[0].model_copy(update={"api_key": "sk-test"}))
check("断网时连通性测试返回失败原因", ok is False and len(msg) > 5, msg[:80])

# ---------------------------------------------------------------- 汇总
fails = [r for r in RESULTS if not r[0]]
print("\n" + "=" * 60)
print(f"共 {len(RESULTS)} 项检查，通过 {len(RESULTS) - len(fails)} 项，失败 {len(fails)} 项")
if fails:
    for _, name, detail in fails:
        print(f"  FAIL: {name} {detail}")
shutil.rmtree(TEST_DATA, ignore_errors=True)
sys.exit(1 if fails else 0)
