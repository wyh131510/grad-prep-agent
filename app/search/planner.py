# -*- coding: utf-8 -*-
"""检索规划器：把选题拆解为子问题 + 中英文查询词（LLM），失败时降级为规则拆解。"""
from __future__ import annotations

import re

from ..llm.client import llm
from ..llm.prompts import plan_prompt
from ..schemas import PlanQuery, PlanSubQuestion, TopicPlan
from ..utils import clean_text


def _fallback_plan(topic: str, major: str) -> TopicPlan:
    """LLM 不可用时的规则降级：选题本身 + 专业组成查询词。"""
    topic = clean_text(topic)
    queries = [PlanQuery(text=topic, lang="zh")]
    if major:
        queries.append(PlanQuery(text=f"{topic} {major}", lang="zh"))
    # 英文查询：提取选题中的拉丁字母词（如 YOLOv8、BERT、3D），组成纯英文查询
    latin = " ".join(set(re.findall(r"[A-Za-z][A-Za-z0-9\-\.]*", topic)))
    if latin:
        queries.append(PlanQuery(text=latin, lang="en"))
    return TopicPlan(
        sub_questions=[
            PlanSubQuestion(question=topic, rationale="选题整体检索（LLM 未配置时降级方案）", queries=queries)
        ]
    )


def plan_topic(topic: str, major: str, years: str, requirements: str, job=None) -> TopicPlan:
    """拆解选题为检索计划。"""
    if job:
        job.update(message="正在用大模型拆解选题，生成子问题与中英文检索词…")
    try:
        data = llm.chat_json(
            role="planner",
            messages=[{"role": "user", "content": plan_prompt(topic, major, years, requirements)}],
            temperature=0.4,
        )
        plan = TopicPlan.model_validate(data)
        # 清洗与校验
        valid = []
        for sq in plan.sub_questions:
            if not sq.question.strip():
                continue
            sq.question = clean_text(sq.question)
            sq.queries = [q for q in sq.queries if q.text.strip()] or [PlanQuery(text=sq.question, lang="zh")]
            valid.append(sq)
        if not valid:
            raise ValueError("空计划")
        return TopicPlan(sub_questions=valid[:8])
    except Exception as exc:  # noqa: BLE001 LLM 未配置/解析失败/格式异常 → 规则降级
        if job:
            job.update(message=f"选题拆解未成功（{type(exc).__name__}: {exc}），使用规则降级方案")
        return _fallback_plan(topic, major)


def collect_queries(plan: TopicPlan) -> list[PlanQuery]:
    """汇总全部查询词（去重；中英文同名查询视为不同查询，避免语言信息丢失）。"""
    seen: set[str] = set()
    out: list[PlanQuery] = []
    for sq in plan.sub_questions:
        for q in sq.queries:
            key = f"{q.lang}|{q.text.strip().lower()}"
            if key not in seen:
                seen.add(key)
                out.append(q)
    return out
