# -*- coding: utf-8 -*-
"""文献理解：单篇结构化总结 + 多篇主题聚类综述。"""
from __future__ import annotations

import json

from ..llm.client import LLMError, llm
from ..llm.prompts import paper_summary_prompt, survey_cluster_prompt, survey_write_prompt
from ..schemas import Paper, PaperSummary, Task
from ..utils import truncate


def _figures_text(paper: Paper) -> str:
    return "\n".join(f"- [图{p.figures.index(f)+1}] {f.caption}" for f in paper.figures if f.caption) or ""


def _snippets_text(paper: Paper) -> str:
    return "\n".join(f"- [{s.section or '正文'}] {s.text}" for s in paper.snippets[:8]) or ""


def summarize_paper(paper: Paper, task: Task, job=None) -> PaperSummary:
    from ..store import repo

    if job:
        job.update(0.2, "精读文献，生成结构化总结…")
    try:
        data = llm.chat_json(
            role="summary",
            messages=[
                {
                    "role": "user",
                    "content": paper_summary_prompt(
                        {
                            "title": paper.title,
                            "authors": paper.authors,
                            "year": paper.year,
                            "venue": paper.venue,
                            "keywords": paper.keywords,
                            "abstract": paper.abstract or paper.abstract_zh,
                            "snippets_text": _snippets_text(paper),
                            "figures_text": _figures_text(paper),
                        },
                        task.topic,
                        task.major,
                    ),
                }
            ],
            temperature=0.3,
        )
    except LLMError as exc:
        raise RuntimeError(f"总结生成失败：{exc}") from exc
    summary = PaperSummary(
        research_question=str(data.get("research_question", "")),
        method=str(data.get("method", "")),
        contributions=[str(c) for c in (data.get("contributions") or [])],
        dataset=str(data.get("dataset", "")),
        metrics=str(data.get("metrics", "")),
        limitations=str(data.get("limitations", "")),
        relevance_to_topic=str(data.get("relevance_to_topic", "")),
        key_points=[str(k) for k in (data.get("key_points") or [])],
        language="zh",
    )
    repo.set_paper_summary(paper.id, summary)
    if job:
        job.update(0.95, "总结完成。")
    return summary


def generate_survey(task: Task, paper_ids: list[str], job=None) -> dict:
    from ..store import repo

    papers = [p for pid in paper_ids if (p := repo.get_paper(pid))]
    if not papers:
        raise ValueError("未找到所选文献")
    numbered = [
        (i, p)
        for i, p in enumerate(papers, 1)
    ]
    paper_list = "\n".join(
        f"{i}. [{p.id}] {p.title} | {(p.abstract or '')[:220]}" for i, p in numbered
    )
    if job:
        job.update(0.15, f"对 {len(papers)} 篇文献进行主题聚类…")
    data = llm.chat_json(
        role="summary",
        messages=[{"role": "user", "content": survey_cluster_prompt(paper_list)}],
        temperature=0.3,
    )
    clusters = data.get("clusters") or []

    # 编号映射：p_xxx → [1]
    id_to_num = {p.id: i for i, p in numbered}
    for c in clusters:
        ids = [pid for pid in (c.get("paper_ids") or []) if pid in id_to_num]
        c["paper_ids"] = ids
        c["refs"] = [f"[{id_to_num[pid]}]" for pid in ids]

    refs_text = "\n".join(
        f"[{i}] {p.title}．{p.venue or '（出处不详）'}，{p.year or '年份不详'}．" for i, p in numbered
    )
    clusters_json = json.dumps(clusters, ensure_ascii=False, indent=2)
    if job:
        job.update(0.55, "聚类完成，撰写结构化综述…")
    content = llm.chat(
        role="summary",
        messages=[
            {
                "role": "user",
                "content": survey_write_prompt(clusters_json, task.topic, task.major, refs_text),
            }
        ],
        temperature=0.4,
        max_tokens=4096,
    )
    repo.save_survey(task.id, content, clusters, [p.id for p in papers])
    if job:
        job.update(0.98, "综述完成。")
    return {"clusters": clusters, "content": content}
