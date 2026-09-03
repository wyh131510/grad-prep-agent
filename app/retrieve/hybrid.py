# -*- coding: utf-8 -*-
"""三重混合检索：BM25 粗筛 → 向量语义匹配 → Reranker 精排，RRF 融合。
返回纯得分映射，由引擎负责持久化（检索模块不依赖存储层）。"""
from __future__ import annotations

from ..llm.client import LLMError, llm
from ..schemas import Paper
from ..utils import rrf_fuse
from . import bm25
from .embedder import embedder
from .reranker import reranker

RERANK_CANDIDATES = 40
LLM_RERANK_CANDIDATES = 15


def hybrid_rank(topic: str, queries: list[str], papers: list[Paper], job=None) -> dict[str, tuple[float, float, float, float]]:
    """返回 {paper_id: (final, bm25, vector, rerank)}，final 为 RRF 融合分 0~1。"""
    ids = [p.id for p in papers]
    docs = [f"{p.title}\n{p.abstract}"[:1200] for p in papers]
    queries = [q for q in queries if q.strip()]
    if not queries:
        queries = [topic] if topic else []

    if job:
        job.update(message=f"第一重检索：BM25 关键词粗筛（{len(papers)} 篇）…")
    bm25_scores = bm25.rank_bm25(docs, queries)

    vec_scores: dict[int, float] = {}
    if embedder.available and queries:
        if job:
            job.update(message="第二重检索：BGE 向量语义匹配…")
        q_vecs = embedder.encode(queries)
        d_vecs = embedder.encode(docs)
        if q_vecs is not None and d_vecs is not None and len(d_vecs):
            q_mean = q_vecs.mean(axis=0)
            norm = float((q_mean @ q_mean) ** 0.5) or 1.0
            q_mean = q_mean / norm
            sims = d_vecs @ q_mean
            for i, s in enumerate(sims):
                vec_scores[i] = round(float(max(0.0, min(1.0, s))), 4)
    elif job:
        job.update(message="未安装本地向量模型，跳过第二重（自动降级）…")

    rerank_scores: dict[int, float] = {}
    if bm25_scores:
        cand = sorted(range(len(ids)), key=lambda i: -bm25_scores.get(i, 0.0))[:RERANK_CANDIDATES]
        if reranker.available:
            if job:
                job.update(message=f"第三重检索：bge-reranker 精排 Top{RERANK_CANDIDATES}…")
            s = reranker.scores(topic or queries[0], [docs[i] for i in cand])
            if s:
                for i, v in zip(cand, s):
                    rerank_scores[i] = round(v, 4)
        else:
            if job:
                job.update(message=f"未安装本地 reranker，使用大模型对 Top{LLM_RERANK_CANDIDATES} 精排…")
            try:
                sub = cand[:LLM_RERANK_CANDIDATES]
                llm_docs = [
                    {"id": ids[i], "title": papers[i].title, "abstract": papers[i].abstract}
                    for i in sub
                ]
                s = llm.rerank_fallback(topic or queries[0], llm_docs)
                for i, v in zip(sub, s):
                    rerank_scores[i] = round(v, 4)
            except LLMError as exc:
                if job:
                    job.update(message=f"LLM 精排不可用（{exc}），仅使用 BM25 排序")

    if job:
        job.update(message="RRF 融合三路得分，生成最终排序…")
    ranked_lists = []
    for score_map in (bm25_scores, vec_scores, rerank_scores):
        if score_map:
            order = sorted(score_map, key=lambda i: -score_map[i])
            ranked_lists.append([ids[i] for i in order])
    if not ranked_lists:
        ranked_lists = [[ids[i] for i in sorted(bm25_scores or {})]] if bm25_scores else [ids]
    fused = rrf_fuse(ranked_lists)

    out: dict[str, tuple[float, float, float, float]] = {}
    for i, pid in enumerate(ids):
        out[pid] = (
            round(fused.get(pid, 0.0), 4),
            round(bm25_scores.get(i, 0.0), 4),
            round(vec_scores.get(i, 0.0), 4),
            round(rerank_scores.get(i, 0.0), 4),
        )
    return out
