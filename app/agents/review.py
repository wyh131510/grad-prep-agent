# -*- coding: utf-8 -*-
"""多智能体评审：4 个角色并行独立评审 + 1 个主席 Agent 做冲突消解与汇总。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from ..llm.client import LLMError, llm
from ..llm.prompts import apply_review_prompt, coordinator_prompt, review_prompt
from ..schemas import MergedReview, ReviewIssue, ReviewResult, Task
from ..utils import clean_text, json_dumps, start_progress_ticker, truncate

REVIEW_ROLES: list[tuple[str, str, str, str]] = [
    (
        "academic", "学术规范评审",
        "选题表述、报告结构完整性、文献引用与标注规范、术语使用与学术语言",
        "引用是否规范（GB/T 7714）、术语前后是否一致、章节结构是否完整、语言是否学术化、有无抄袭痕迹",
    ),
    (
        "logic", "逻辑评审",
        "研究问题、研究内容与技术路线之间的逻辑关系",
        "研究问题是否聚焦；研究内容与目标是否回应研究问题；技术路线各环节是否衔接、有无跳跃或自相矛盾；预期成果与目标是否对应",
    ),
    (
        "feasibility", "可行性评审",
        "方法与工作量",
        "方法是否可行、数据/软硬件/实验条件是否具备；工作量与进度安排是否匹配；有无风险预案或备选方案",
    ),
    (
        "format", "格式评审",
        "与学校开题模板的符合度",
        "逐项对照学校模板：章节是否齐全、格式要求（字数、图表编号、参考文献格式、字体等）是否满足、有无缺失栏目",
    ),
]


def _materials_brief(task: Task) -> str:
    from ..store import repo

    _, papers = repo.list_papers(task.id, collected=True, sort="score", limit=60)
    return "\n".join(f"- {p.title}（{p.year or '?'}）" for p in papers)[:3000]


def _clean_issues(items) -> list[ReviewIssue]:
    out = []
    for it in (items or [])[:10]:
        if not isinstance(it, dict):
            continue
        sev = str(it.get("severity", "medium"))
        if sev not in ("high", "medium", "low"):
            sev = "medium"
        out.append(
            ReviewIssue(
                severity=sev,
                section=str(it.get("section", "overall")),
                problem=str(it.get("problem", "")),
                suggestion=str(it.get("suggestion", "")),
                evidence=str(it.get("evidence", "")),
            )
        )
    return out


def _review_one(role: tuple, proposal_text: str, template_hint: str, materials: str) -> ReviewResult:
    key, name, scope, criteria = role
    prov = llm.resolve(key)
    data = llm.chat_json(
        role=key,
        messages=[
            {
                "role": "user",
                "content": review_prompt(name, scope, criteria, proposal_text[:14000], template_hint, materials),
            }
        ],
        temperature=0.2,
        max_tokens=3500,
    )
    score = int(data.get("score", 0))
    score = max(0, min(100, score))
    return ReviewResult(
        agent=key,
        agent_name=name,
        provider_id=prov.id,
        model=prov.model,
        score=score,
        summary=str(data.get("summary", "")),
        issues=_clean_issues(data.get("issues")),
    )


def run_review(task: Task, job=None) -> dict:
    from ..store import repo

    proposal_text = clean_text(_assemble(task))
    if len(proposal_text) < 200:
        raise ValueError("开题报告内容过少，请先生成各分块后再评审")
    tmpl = repo.get_template(task.id)
    template_hint = truncate(clean_text(tmpl.content_md), 3000) if tmpl else ""
    materials = _materials_brief(task)

    if job:
        job.update(0.08, "四位评审专家并行独立评审中（学术规范 / 逻辑 / 可行性 / 格式）…")
    results: list[ReviewResult] = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(_review_one, role, proposal_text, template_hint, materials): role for role in REVIEW_ROLES}
        for i, fut in enumerate(futures, 1):
            try:
                results.append(fut.result())
            except LLMError as exc:
                if job:
                    job.update(message=f"{futures[fut][1]} 评审失败：{exc}")
            except Exception as exc:  # noqa: BLE001
                if job:
                    job.update(message=f"{futures[fut][1]} 评审异常：{exc}")
            if job:
                job.update(0.1 + 0.45 * i / len(REVIEW_ROLES), f"评审进度 {i}/{len(REVIEW_ROLES)}…")

    if not results:
        raise RuntimeError("全部评审 Agent 均失败，请检查大模型服务商配置")

    if job:
        job.update(0.6, "评审完成，主席 Agent 进行冲突消解与一致性汇总…")
    merged_data = llm.chat_json(
        role="coordinator",
        messages=[
            {
                "role": "user",
                "content": coordinator_prompt(
                    json_dumps([r.model_dump() for r in results]), task.topic
                ),
            }
        ],
        temperature=0.2,
        max_tokens=3500,
    )
    merged = MergedReview(
        overall_score=max(0, min(100, int(merged_data.get("overall_score") or 0))),
        verdict=str(merged_data.get("verdict", "修改后通过")),
        conflicts=[dict(c) for c in (merged_data.get("conflicts") or []) if isinstance(c, dict)][:8],
        final_suggestions=[
            {
                "priority": int(s.get("priority", i + 1)),
                "section": str(s.get("section", "overall")),
                "action": str(s.get("action", "")),
                "reason": str(s.get("reason", "")),
            }
            for i, s in enumerate((merged_data.get("final_suggestions") or [])[:15])
            if isinstance(s, dict)
        ],
        strengths=[str(x) for x in (merged_data.get("strengths") or [])][:8],
    )

    for r in results:
        repo.save_review(task.id, r.agent, r.model_dump())
    repo.save_review(task.id, "merged", merged.model_dump())
    if job:
        job.update(0.98, "多智能体评审完成。")
    return {"results": [r.model_dump() for r in results], "merged": merged.model_dump()}


def _assemble(task: Task) -> str:
    from ..agents.proposal import assemble_text

    return assemble_text(task)


def apply_review(task: Task, section_key: str, instruction: str = "", job=None) -> dict:
    from ..store import repo

    by_key = {s.key: s for s in repo.get_sections(task.id)}
    if section_key not in by_key:
        raise ValueError(f"未知分块：{section_key}")
    section = by_key[section_key]
    if not section.content.strip():
        raise ValueError("该分块还没有内容，请先生成")

    issues_text = ""
    for r in repo.get_reviews(task.id):
        rel = [i for i in r.issues if i.section in (section_key, "overall")]
        if rel:
            issues_text += f"\n【{r.agent_name}】\n" + "\n".join(
                f"- [{i.severity}] {i.problem} → 建议：{i.suggestion}" for i in rel
            )
    merged = repo.get_merged(task.id)
    suggestions_text = ""
    if merged:
        rel = [s for s in merged.final_suggestions if s.section in (section_key, "overall")]
        suggestions_text = "\n".join(
            f"- P{s.priority}: {s.action}（{s.reason}）" for s in rel
        )

    if job:
        job.update(0.3, f"根据评审意见修改「{section.title}」…（调用大模型改写，可能需 30~90 秒）")
    stop = start_progress_ticker(job, f"根据评审意见修改「{section.title}」")
    messages = [
        {
            "role": "user",
            "content": apply_review_prompt(
                section.title, section.content, issues_text, suggestions_text, instruction
            ),
        }
    ]
    try:
        content = llm.chat(role="proposal", messages=messages, temperature=0.4, max_tokens=4096).strip()
    except LLMError:
        # DeepSeek 偶发"空回复/拒答"（尤其改写参考文献时）：附引导后重试一次
        messages += [
            {"role": "assistant", "content": "（模型未输出可用内容）"},
            {
                "role": "user",
                "content": "请直接输出修改后的完整分块内容（Markdown，以“## {0}”开头），不要输出空内容、说明或分析。".format(
                    section.title
                ),
            },
        ]
        content = llm.chat(role="proposal", messages=messages, temperature=0.5, max_tokens=4096).strip()
    finally:
        stop()
    repo.put_section(task.id, section_key, section.title, content, "edited")
    # 新旧内容差异（让用户明确知道改了什么）
    diff = _make_diff(section.content, content)
    # 标记该节相关意见为"已处理"（前端隐藏其「辅助修改」按钮；新一轮整体评审会重新生成）
    _mark_applied(task.id, section_key)
    if job:
        job.update(0.98, "修改完成。")
    return {"key": section_key, "content": content, "diff": diff}


def _mark_applied(task_id: str, section_key: str) -> None:
    """标记与已修改分块相关的评审意见/汇总建议为已处理（applied=True）。"""
    from ..store import repo

    for r in repo.get_reviews(task_id):
        changed = False
        for i in r.issues:
            if i.section in (section_key, "overall") and not i.applied:
                i.applied = True
                changed = True
        if changed:
            repo.save_review(task_id, r.agent, r.model_dump())
    merged = repo.get_merged(task_id)
    if merged:
        changed = False
        for s in merged.final_suggestions:
            if s.section in (section_key, "overall") and not s.applied:
                s.applied = True
                changed = True
        if changed:
            repo.save_review(task_id, "merged", merged.model_dump())


def _make_diff(old: str, new: str, max_lines: int = 120) -> str:
    """difflib 统一差异文本（- 删除行 / + 新增行），限制行数避免过大。"""
    import difflib

    old_lines = old.splitlines()
    new_lines = new.splitlines()
    text = "\n".join(
        difflib.unified_diff(old_lines, new_lines, fromfile="原内容", tofile="修改后", lineterm="", n=1)
    )
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"……（共 {len(lines)} 行差异，其余省略）"]
    return "\n".join(lines)
