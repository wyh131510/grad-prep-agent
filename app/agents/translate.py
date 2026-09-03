# -*- coding: utf-8 -*-
"""高质量英译中：先建术语对照表（保证一致性），再分块翻译标题、摘要与关键片段。
对空回复/截断回复自动重试，单块失败不阻塞整体。"""
from __future__ import annotations

from ..llm.client import LLMError, llm
from ..llm.prompts import glossary_prompt, translate_prompt
from ..schemas import Paper, Task, TranslationResult
from ..utils import chunk_text


def _translate_block(text: str, glossary: dict, context: str, role: str = "translate") -> str:
    """翻译一块文本；空/过短结果自动补译一次。"""
    translated = llm.chat(
        role=role,
        messages=[{"role": "user", "content": translate_prompt(text, glossary, context)}],
        temperature=0.2,
        max_tokens=4096,
    ).strip()
    if len(translated) < max(20, len(text) * 0.25):
        # 疑似截断：要求补全后重新输出
        translated = llm.chat(
            role=role,
            messages=[
                {"role": "user", "content": translate_prompt(text, glossary, context)},
                {"role": "assistant", "content": translated},
                {"role": "user", "content": "以上译文不完整，请给出完整、无省略的译文。"},
            ],
            temperature=0.2,
            max_tokens=4096,
        ).strip()
    return translated


def translate_paper(paper: Paper, task: Task, job=None) -> TranslationResult:
    from ..store import repo

    if job:
        job.update(0.1, "第一步：从文献样本建立领域术语对照表（保证术语一致）…")
    domain = f"{task.major or ''} {task.topic}"[:120]
    sample = f"标题：{paper.title}\n摘要：{(paper.abstract or '')[:1500]}"
    glossary: dict[str, str] = {}
    try:
        data = llm.chat_json(
            role="translate",
            messages=[{"role": "user", "content": glossary_prompt(domain, sample)}],
            temperature=0.2,
        )
        glossary = {
            str(k): str(v)
            for k, v in (data.get("glossary") or {}).items()
            if str(k).strip() and str(v).strip()
        }
    except LLMError:
        if job:
            job.update(message="术语表生成失败，直接翻译（一致性可能下降）…")

    if job:
        job.update(0.3, f"术语表 {len(glossary)} 条。第二步：翻译标题…")
    title_zh = _translate_block(paper.title, glossary, "文献标题")

    chunks = chunk_text(paper.abstract, max_chars=2200, overlap=120)
    parts: list[str] = []
    for i, ch in enumerate(chunks):
        if job:
            job.update(0.35 + 0.45 * (i + 1) / max(1, len(chunks)), f"翻译摘要第 {i + 1}/{len(chunks)} 块…")
        parts.append(_translate_block(ch, glossary, "文献摘要"))
    abstract_zh = "\n\n".join(parts)

    # 关键片段翻译（尽力而为，失败不影响整体）
    snippets_zh: list[str] = []
    if paper.snippets:
        if job:
            job.update(0.85, "翻译关键片段…")
        for s in paper.snippets[:5]:
            try:
                snippets_zh.append(_translate_block(s.text, glossary, "文献关键片段"))
            except LLMError:
                snippets_zh.append("")

    tr = TranslationResult(
        title_zh=title_zh,
        abstract_zh=abstract_zh,
        snippets_zh=snippets_zh,
        glossary=glossary,
        quality_note=(
            f"术语一致性已按 {len(glossary)} 条对照表对齐"
            + (f"；摘要分 {len(chunks)} 块翻译后合并" if len(chunks) > 1 else "")
            + (f"；已翻译 {len([s for s in snippets_zh if s])} 条关键片段" if snippets_zh else "")
        ),
    )
    repo.set_paper_translation(paper.id, tr)
    if job:
        job.update(0.98, "翻译完成。")
    return tr
