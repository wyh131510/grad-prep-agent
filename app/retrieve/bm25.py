# -*- coding: utf-8 -*-
"""BM25 关键词粗筛（第一重）。rank_bm25 缺失时使用内置同参数实现，保证核心检索可用。"""
from __future__ import annotations

import math
from collections import Counter

from .tokenize import tokenize

try:
    from rank_bm25 import BM25Okapi
except ImportError:  # pragma: no cover
    BM25Okapi = None


class _MiniBM25:
    """标准 BM25 的轻量实现（Okapi BM25，k1=1.5，b=0.75）。"""

    def __init__(self, corpus: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.docs = corpus
        self.doc_len = [len(d) for d in corpus]
        self.avgdl = (sum(self.doc_len) / len(corpus)) if corpus else 1.0
        df: dict[str, int] = {}
        for doc in corpus:
            for t in set(doc):
                df[t] = df.get(t, 0) + 1
        n = len(corpus)
        self.idf = {t: math.log((n - d + 0.5) / (d + 0.5) + 1.0) for t, d in df.items()}

    def get_scores(self, query: list[str]) -> list[float]:
        out: list[float] = []
        for dl, doc in zip(self.doc_len, self.docs):
            tf = Counter(doc)
            score = 0.0
            for t in set(query):
                if t not in self.idf:
                    continue
                ft = tf.get(t, 0)
                if ft:
                    score += (
                        self.idf[t]
                        * (ft * (self.k1 + 1.0))
                        / (ft + self.k1 * (1.0 - self.b + self.b * dl / self.avgdl))
                    )
            out.append(score)
        return out


def rank_bm25(docs: list[str], queries: list[str], top_k: int | None = None) -> dict[int, float]:
    """返回 {doc_index: 得分(0~1)}：每个查询打分后按最大值归一，取跨查询最大值。

    实现选择：rank_bm25 的 idf 公式在小语料会退化为 0（log((N-1+0.5)/(1+0.5))=log(1)），
    因此小语料（<100 篇）使用带 +1 平滑的内置实现；大语料使用 rank_bm25 原生实现。
    """
    if not docs or not queries:
        return {}
    corpus = [tokenize(d) for d in docs]
    if len(corpus) >= 100 and BM25Okapi is not None:
        bm25 = BM25Okapi(corpus)
    else:
        bm25 = _MiniBM25(corpus)
    best: dict[int, float] = {}
    for q in queries:
        qt = tokenize(q)
        if not qt:
            continue
        scores = list(bm25.get_scores(qt))
        mx = max(scores) if scores else 0.0
        if mx <= 0:
            continue
        for i, s in enumerate(scores):
            v = float(s) / mx
            if v > best.get(i, 0.0):
                best[i] = v
    if top_k is not None:
        top = sorted(best, key=lambda i: -best[i])[:top_k]
        return {i: best[i] for i in top}
    return best
