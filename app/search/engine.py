# -*- coding: utf-8 -*-
"""检索流水线编排：
选题拆解 → 多源并行抓取 → 统一解析 → 去重合并入库 → 年份过滤 → 三重混合检索排序。
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from ..config import get_settings
from ..parse import html_parser, pdf_parser, unifier
from ..parse.importers import parse_import_text
from ..retrieve import hybrid
from ..schemas import Task
from ..utils import make_id, now_iso
from . import planner
from .arxiv import ArxivSource
from .base import SearchHit, SearchSourceError, SourceAdapter
from .cnki import CnkiSource  # noqa: F401  反爬限制，保留代码供内网环境使用，默认不可选
from .crossref import CrossrefSource
from .direct_url import DirectUrlSource, looks_like_pdf
from .openalex import OpenAlexSource
from .pubmed import PubMedSource
from .semantic_scholar import SemanticScholarSource
from .wanfang import WanfangSource  # noqa: F401  页面改版，保留代码备用，默认不可选

SOURCE_REGISTRY: dict[str, type[SourceAdapter]] = {
    "semantic_scholar": SemanticScholarSource,
    "arxiv": ArxivSource,
    "crossref": CrossrefSource,
    "pubmed": PubMedSource,
    "openalex": OpenAlexSource,
}

DEFAULT_SOURCES = ["semantic_scholar", "arxiv", "crossref", "pubmed", "openalex"]
QUERIES_PER_SOURCE = 6


def build_sources(task: Task, timeout: int) -> list[SourceAdapter]:
    names = task.sources or DEFAULT_SOURCES
    sources: list[SourceAdapter] = []
    for name in names:
        cls = SOURCE_REGISTRY.get(name)
        if cls:
            sources.append(cls(timeout=timeout))
    return sources


def _queries_for(source: SourceAdapter, queries: list) -> list:
    if not source.langs:
        return []
    return [q for q in queries if q.lang in source.langs][:QUERIES_PER_SOURCE]


def _in_year_range(paper, year_from, year_to) -> bool:
    if paper.year is None:
        return True
    if year_from and paper.year < year_from:
        return False
    if year_to and paper.year > year_to:
        return False
    return True


def _upsert_merged(task_id: str, papers: dict[str, "unifier.Paper"]) -> None:
    """与库中已有同 id 文献合并后入库。"""
    from ..store import repo

    for pid, p in papers.items():
        old = repo.get_paper(pid)
        if old and old.task_id == task_id:
            p = unifier.merge_paper(old, p)
        repo.upsert_paper(p)


def run_search_pipeline(task: Task, feedback: str, job) -> dict:
    from ..store import repo

    repo.set_task_status(task.id, "searching")
    if feedback.strip():
        repo.set_task_feedback(task.id, feedback)
        task.feedback = feedback.strip()

    opts = get_settings().search_options
    years = f"{task.year_from or '不限'} ~ {task.year_to or '不限'}"
    job.update(0.03, "第一步：拆解选题，生成检索子问题与中英文查询词…")
    plan = planner.plan_topic(task.topic, task.major, years, task.requirements, job=job)
    repo.set_task_plan(task.id, plan)
    queries = planner.collect_queries(plan)

    job.update(0.10, f"拆解完成：{len(plan.sub_questions)} 个子问题、{len(queries)} 个查询词，开始多源并行抓取…")

    sources = build_sources(task, opts.request_timeout)
    work_items = [(src, q) for src in sources for q in _queries_for(src, queries)]
    per_query_limit = max(3, opts.max_results_per_source // max(1, len(work_items) // len(sources)))
    per_query_limit = max(2, min(per_query_limit, 8))

    hits: dict[str, list[SearchHit]] = {src.id: [] for src in sources}
    failures: dict[str, str] = {}
    total_items = max(1, len(work_items))
    done = 0

    def work(item):
        src, q = item
        try:
            return src.id, src.search(q.text, task.year_from, task.year_to, per_query_limit), None
        except SearchSourceError as exc:
            return src.id, [], str(exc)
        except Exception as exc:  # noqa: BLE001 单条查询失败不拖垮整个流水线
            return src.id, [], f"{type(exc).__name__}: {exc}"

    with ThreadPoolExecutor(max_workers=4) as ex:
        for src_id, found, err in ex.map(work, work_items):
            done += 1
            if err:
                failures.setdefault(src_id, err)
            else:
                hits[src_id].extend(found)
            job.update(
                0.10 + 0.40 * done / total_items,
                f"多源抓取中（{done}/{total_items}）… 已命中 {sum(len(v) for v in hits.values())} 篇",
            )

    # 每源结果数上限
    for src_id in hits:
        hits[src_id] = hits[src_id][: opts.max_results_per_source]

    all_hits = [h for lst in hits.values() for h in lst]
    job.update(0.52, f"共抓取 {len(all_hits)} 条命中，统一解析、清洗与去重…")

    papers: dict[str, object] = {}
    for h in all_hits:
        h.extra["_source"] = _source_of(h, hits)
        p = unifier.hit_to_paper(h, task.id)
        if p.id in papers:
            papers[p.id] = unifier.merge_paper(papers[p.id], p)
        else:
            papers[p.id] = p
    _upsert_merged(task.id, papers)

    # PubMed/PMC 文献：从来源页提取真实图表（轻量，每篇限 3 张）
    from ..parse.page_figures import fetch_page_figures

    pubmed_papers = [p for p in papers.values() if p.source == "pubmed" and p.url and not p.figures]
    if pubmed_papers:
        job.update(message=f"从 PubMed 来源页提取 {len(pubmed_papers)} 篇文献的图表…")
        for p in pubmed_papers[:10]:
            try:
                figs = fetch_page_figures(p, max_figures=3)
                if figs:
                    p.figures = figs
            except Exception:  # noqa: BLE001
                continue
        _upsert_merged(task.id, papers)

    # ---- 用户提供的直链 URL
    if task.urls:
        job.update(0.56, f"抓取并解析用户提供的 {len(task.urls)} 个 URL（HTML/PDF）…")
        keywords = [q.text for q in queries]
        for i, url in enumerate(task.urls[:20]):
            try:
                for u, ctype, content in DirectUrlSource(timeout=opts.request_timeout).fetch_documents([url]):
                    paper_id = f"p_{make_id(f'paper|{u}', length=16)}"
                    if looks_like_pdf(u, ctype) or content[:4] == b"%PDF":
                        parsed = pdf_parser.parse_pdf(content, task.id, paper_id, keywords, url=u, pdf_url=u)
                    else:
                        parsed = html_parser.parse_html(u, content.decode("utf-8", errors="replace"), keywords)
                    p = unifier.parsed_to_paper(parsed, task.id, "direct_url", paper_id=paper_id)
                    if _in_year_range(p, task.year_from, task.year_to):
                        papers[p.id] = p
            except Exception as exc:  # noqa: BLE001
                job.update(message=f"URL 抓取失败 {url[:80]}：{exc}")
        _upsert_merged(task.id, papers)

    # ---- 年份过滤 + 空标题过滤
    kept = [p for p in papers.values() if _in_year_range(p, task.year_from, task.year_to) and p.title.strip()]
    job.update(0.60, f"过滤后保留 {len(kept)} 篇，开始三重混合检索排序…")

    query_texts = [q.text for q in queries] + [task.topic]
    scores = hybrid.hybrid_rank(task.topic, query_texts, kept, job=job)
    for pid, (final, b, v, r) in scores.items():
        repo.update_paper_scores(pid, final, b, v, r)

    repo.set_task_status(task.id, "searched")
    job.update(0.99, "检索完成。")
    return {
        "papers": len(kept),
        "plan": plan.model_dump(),
        "queries": len(queries),
        "sources_ok": [sid for sid in hits if hits[sid]],
        "sources_failed": failures,
    }


def _source_of(hit: SearchHit, hits: dict[str, list[SearchHit]]) -> str:
    for sid, lst in hits.items():
        if hit in lst:
            return sid
    return "unknown"


def import_documents(task: Task, filename: str, data: bytes, job) -> dict:
    """导入知网等导出的 EndNote/RIS 文本文件。"""
    from ..store import repo

    text = data.decode("utf-8", errors="replace")
    records = parse_import_text(text)
    job.update(0.3, f"解析到 {len(records)} 条文献记录，入库…")
    papers: dict[str, object] = {}
    for r in records:
        if not r["title"]:
            continue
        hit = SearchHit(
            title=r["title"], abstract=r["abstract"], authors=r["authors"], year=r["year"],
            venue=r["venue"], doi=r["doi"], keywords=r["keywords"], url=r["url"], pdf_url=r["pdf_url"],
            extra={"_source": "import"},
        )
        p = unifier.hit_to_paper(hit, task.id)
        if p.id in papers:
            papers[p.id] = unifier.merge_paper(papers[p.id], p)
        else:
            papers[p.id] = p
    _upsert_merged(task.id, papers)
    repo.set_task_status(task.id, "searched")
    return {"imported": len(papers), "filename": filename}
