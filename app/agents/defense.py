# -*- coding: utf-8 -*-
"""答辩问题清单：基于开题报告预测评委提问，附考察意图与回答要点。"""
from __future__ import annotations

from ..llm.client import llm
from ..llm.prompts import defense_prompt
from ..schemas import Task
from ..utils import clean_text


def generate_defense(task: Task, job=None) -> str:
    from ..store import repo

    from .proposal import assemble_text

    proposal = clean_text(assemble_text(task))
    if len(proposal) < 200:
        raise ValueError("开题报告内容过少，请先生成后再生成答辩问题")
    _, papers = repo.list_papers(task.id, collected=True, sort="score", limit=30)
    materials = "\n".join(f"- {p.title}（{p.year or '?'}）" for p in papers)[:2000]

    if job:
        job.update(0.3, "基于开题报告预测答辩问题…")
    data = llm.chat_json(
        role="defense",
        messages=[
            {
                "role": "user",
                "content": defense_prompt(task.topic, task.major, proposal[:14000], materials),
            }
        ],
        temperature=0.4,
        max_tokens=3500,
    )
    md = _render(data)
    repo.save_defense(task.id, md)
    if job:
        job.update(0.98, "答辩问题清单已生成。")
    return md


def _render(data: dict) -> str:
    lines = ["# 开题答辩问题清单", ""]
    for i, cat in enumerate(data.get("categories") or [], 1):
        lines.append(f"## {i}. {cat.get('name', '')}")
        for j, q in enumerate(cat.get("questions") or [], 1):
            lines.append(f"\n**Q{i}.{j}　{q.get('question', '')}**")
            if q.get("intent"):
                lines.append(f"\n- 考察意图：{q['intent']}")
            if q.get("hint"):
                lines.append(f"- 参考要点：{q['hint']}")
        lines.append("")
    return "\n".join(lines)
