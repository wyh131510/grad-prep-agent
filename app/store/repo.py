# -*- coding: utf-8 -*-
"""领域仓库：任务/文献/开题分块/评审/答辩/模板/综述 的 CRUD。"""
from __future__ import annotations

import json

from ..db import db
from ..schemas import (
    MergedReview,
    Paper,
    PaperSummary,
    ProposalSection,
    ReviewResult,
    Task,
    TaskCreate,
    TemplateInfo,
    TopicPlan,
    TranslationResult,
)
from ..utils import json_dumps, make_id, now_iso

# ================================================================ 任务


def _task_row_to_model(r: dict, counts: dict | None = None) -> Task:
    return Task(
        id=r["id"],
        topic=r["topic"],
        major=r.get("major", ""),
        year_from=r.get("year_from"),
        year_to=r.get("year_to"),
        sources=json.loads(r.get("sources") or "[]"),
        requirements=r.get("requirements", ""),
        feedback=r.get("feedback", ""),
        urls=json.loads(r.get("urls") or "[]"),
        status=r.get("status", "created"),
        plan=json.loads(r["plan"]) if r.get("plan") else None,
        paper_count=(counts or {}).get("paper_count", r.get("paper_count", 0)),
        collected_count=(counts or {}).get("collected_count", r.get("collected_count", 0)),
        created_at=r.get("created_at", ""),
        updated_at=r.get("updated_at", ""),
    )


def create_task(tc: TaskCreate) -> Task:
    task_id = f"t_{make_id(f'task|{tc.topic}|{now_iso()}', length=12)}"
    db.execute(
        """INSERT INTO tasks (id, topic, major, year_from, year_to, sources, requirements,
                              feedback, status, plan, urls, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            task_id, tc.topic.strip(), tc.major.strip(), tc.year_from, tc.year_to,
            json_dumps(tc.sources), tc.requirements.strip(), "",
            "created", None, json_dumps(tc.urls), now_iso(), now_iso(),
        ),
    )
    return get_task(task_id)


def get_task(task_id: str) -> Task | None:
    r = db.query_one(
        """SELECT t.*,
                  (SELECT COUNT(*) FROM papers p WHERE p.task_id = t.id) AS paper_count,
                  (SELECT COUNT(*) FROM papers p WHERE p.task_id = t.id AND p.collected = 1) AS collected_count
           FROM tasks t WHERE t.id = ?""",
        (task_id,),
    )
    return _task_row_to_model(r) if r else None


def list_tasks() -> list[Task]:
    rows = db.query(
        """SELECT t.*,
                  (SELECT COUNT(*) FROM papers p WHERE p.task_id = t.id) AS paper_count,
                  (SELECT COUNT(*) FROM papers p WHERE p.task_id = t.id AND p.collected = 1) AS collected_count
           FROM tasks t ORDER BY t.created_at DESC"""
    )
    return [_task_row_to_model(r) for r in rows]


def delete_task(task_id: str) -> None:
    for table in ("papers", "proposals", "reviews", "defense", "templates", "surveys", "tasks"):
        db.execute(f"DELETE FROM {table} WHERE {'task_id' if table != 'tasks' else 'id'} = ?", (task_id,))


def set_task_status(task_id: str, status: str) -> None:
    db.execute("UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?", (status, now_iso(), task_id))


def update_task(task_id: str, fields: dict) -> Task | None:
    """编辑任务参数（选题/专业/年份/来源/要求/直链）。"""
    scalar = {"topic", "major", "year_from", "year_to", "requirements"}
    json_cols = {"sources", "urls"}
    sets: list[str] = []
    params: list = []
    for k in scalar:
        if k in fields and fields[k] is not None:
            sets.append(f"{k}=?")
            params.append(fields[k])
    for k in json_cols:
        if k in fields and fields[k] is not None:
            sets.append(f"{k}=?")
            params.append(json_dumps(fields[k]))
    if not sets:
        return get_task(task_id)
    sets.append("updated_at=?")
    params += [now_iso(), task_id]
    db.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id=?", params)
    return get_task(task_id)


def set_task_plan(task_id: str, plan: TopicPlan) -> None:
    db.execute("UPDATE tasks SET plan = ?, updated_at = ? WHERE id = ?", (json_dumps(plan.model_dump()), now_iso(), task_id))


def set_task_feedback(task_id: str, feedback: str) -> None:
    db.execute("UPDATE tasks SET feedback = ?, updated_at = ? WHERE id = ?", (feedback.strip(), now_iso(), task_id))


# ================================================================ 文献

_PAPER_JSON_FIELDS = ("authors", "keywords", "snippets", "figures", "summary", "translation")


def _paper_row_to_model(r: dict) -> Paper:
    data = dict(r)
    for f in _PAPER_JSON_FIELDS:
        raw = data.get(f)
        data[f] = json.loads(raw) if raw else ([] if f in ("authors", "keywords", "snippets", "figures") else None)
    data["collected"] = bool(data.get("collected"))
    data["is_open_access"] = bool(data.get("is_open_access"))
    return Paper(**{k: v for k, v in data.items() if k in Paper.model_fields})


def _paper_to_row(p: Paper) -> dict:
    d = p.model_dump()
    for f in _PAPER_JSON_FIELDS:
        d[f] = json_dumps(d.get(f) or ([] if f in ("authors", "keywords", "snippets", "figures") else None))
    d["collected"] = 1 if d["collected"] else 0
    d["is_open_access"] = 1 if d["is_open_access"] else 0
    return d


def upsert_paper(p: Paper) -> None:
    row = _paper_to_row(p)
    db.upsert(
        "papers",
        row,
        conflict_cols=["id"],
        update_cols=[k for k in row if k != "id"],
    )


def get_paper(paper_id: str) -> Paper | None:
    r = db.query_one("SELECT * FROM papers WHERE id = ?", (paper_id,))
    return _paper_row_to_model(r) if r else None


_SORT_COLS = {"score": "score", "year": "year", "citations": "citations", "title": "title"}


def list_papers(
    task_id: str | None = None,
    q: str = "",
    year_from: int | None = None,
    year_to: int | None = None,
    source: str = "",
    collected: bool | None = None,
    sort: str = "score",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[Paper]]:
    where: list[str] = []
    params: list = []
    if task_id:
        where.append("task_id = ?")
        params.append(task_id)
    if q:
        like = f"%{q}%"
        where.append("(title LIKE ? OR abstract LIKE ? OR title_zh LIKE ? OR abstract_zh LIKE ?)")
        params += [like] * 4
    if year_from:
        where.append("(year >= ? OR year IS NULL)")
        params.append(year_from)
    if year_to:
        where.append("(year <= ? OR year IS NULL)")
        params.append(year_to)
    if source:
        where.append("source = ?")
        params.append(source)
    if collected is not None:
        where.append("collected = ?")
        params.append(1 if collected else 0)
    where_sql = " AND ".join(where) or "1=1"
    total = db.query_one(f"SELECT COUNT(*) AS c FROM papers WHERE {where_sql}", params)["c"]
    col = _SORT_COLS.get(sort, "score")
    direction = "DESC" if order == "desc" else "ASC"
    rows = db.query(
        f"SELECT * FROM papers WHERE {where_sql} ORDER BY {col} {direction}, id LIMIT ? OFFSET ?",
        params + [limit, offset],
    )
    return total, [_paper_row_to_model(r) for r in rows]


def update_paper_scores(paper_id: str, final: float, bm25: float, vector: float, rerank: float) -> None:
    db.execute(
        "UPDATE papers SET score=?, bm25_score=?, vector_score=?, rerank_score=? WHERE id=?",
        (final, bm25, vector, rerank, paper_id),
    )


def set_paper_collected(paper_id: str, collected: bool, file_path: str = "") -> None:
    db.execute(
        "UPDATE papers SET collected = ?, file_path = ? WHERE id = ?",
        (1 if collected else 0, file_path, paper_id),
    )


def set_paper_summary(paper_id: str, summary: PaperSummary) -> None:
    db.execute("UPDATE papers SET summary = ? WHERE id = ?", (json_dumps(summary.model_dump()), paper_id))


def set_paper_translation(paper_id: str, tr: TranslationResult) -> None:
    db.execute(
        "UPDATE papers SET translation = ?, title_zh = ?, abstract_zh = ? WHERE id = ?",
        (json_dumps(tr.model_dump()), tr.title_zh, tr.abstract_zh, paper_id),
    )


# ================================================================ 开题分块


def get_sections(task_id: str) -> list[ProposalSection]:
    rows = db.query("SELECT * FROM proposals WHERE task_id = ?", (task_id,))
    return [ProposalSection(**{k: r[k] for k in ("key", "title", "content", "status", "updated_at")}) for r in rows]


def put_section(task_id: str, key: str, title: str, content: str, status: str = "draft") -> None:
    db.upsert(
        "proposals",
        {"task_id": task_id, "key": key, "title": title, "content": content, "status": status, "updated_at": now_iso()},
        conflict_cols=["task_id", "key"],
    )


def ensure_sections(task_id: str, sections: list[tuple[str, str]]) -> None:
    for key, title in sections:
        db.execute(
            "INSERT OR IGNORE INTO proposals (task_id, key, title, content, status, updated_at) VALUES (?,?,?,?,?,?)",
            (task_id, key, title, "", "empty", now_iso()),
        )


# ================================================================ 评审 / 答辩 / 模板 / 综述


def save_review(task_id: str, agent: str, result: dict) -> None:
    db.upsert(
        "reviews",
        {"task_id": task_id, "agent": agent, "result": json_dumps(result), "created_at": now_iso()},
        conflict_cols=["task_id", "agent"],
    )


def get_reviews(task_id: str) -> list[ReviewResult]:
    rows = db.query("SELECT * FROM reviews WHERE task_id = ? AND agent != 'merged'", (task_id,))
    return [ReviewResult(**json.loads(r["result"])) for r in rows]


def get_merged(task_id: str) -> MergedReview | None:
    r = db.query_one("SELECT * FROM reviews WHERE task_id = ? AND agent = 'merged'", (task_id,))
    return MergedReview(**json.loads(r["result"])) if r else None


def save_defense(task_id: str, content: str) -> None:
    db.upsert("defense", {"task_id": task_id, "content": content, "created_at": now_iso()}, conflict_cols=["task_id"])


def get_defense(task_id: str) -> dict | None:
    r = db.query_one("SELECT content, created_at FROM defense WHERE task_id = ?", (task_id,))
    return dict(r) if r else None


def save_template(task_id: str, info: TemplateInfo) -> None:
    db.upsert(
        "templates",
        {
            "task_id": task_id,
            "filename": info.filename,
            "content_md": info.content_md,
            "sections": json_dumps(info.sections),
            "uploaded_at": now_iso(),
        },
        conflict_cols=["task_id"],
    )


def get_template(task_id: str) -> TemplateInfo | None:
    r = db.query_one("SELECT * FROM templates WHERE task_id = ?", (task_id,))
    if not r:
        return None
    return TemplateInfo(filename=r["filename"], content_md=r["content_md"], sections=json.loads(r["sections"] or "[]"))


def save_survey(task_id: str, content: str, clusters: list[dict], paper_ids: list[str]) -> None:
    db.upsert(
        "surveys",
        {
            "task_id": task_id,
            "content": content,
            "clusters": json_dumps(clusters),
            "paper_ids": json_dumps(paper_ids),
            "created_at": now_iso(),
        },
        conflict_cols=["task_id"],
    )


def get_survey(task_id: str) -> dict | None:
    r = db.query_one("SELECT * FROM surveys WHERE task_id = ?", (task_id,))
    if not r:
        return None
    return {
        "content": r["content"],
        "clusters": json.loads(r["clusters"] or "[]"),
        "paper_ids": json.loads(r["paper_ids"] or "[]"),
        "created_at": r["created_at"],
    }


def stats() -> dict:
    tasks = db.query_one("SELECT COUNT(*) AS c FROM tasks")["c"]
    papers = db.query_one("SELECT COUNT(*) AS c FROM papers")["c"]
    collected = db.query_one("SELECT COUNT(*) AS c FROM papers WHERE collected = 1")["c"]
    drafts = db.query_one("SELECT COUNT(DISTINCT task_id) AS c FROM proposals WHERE content != ''")["c"]
    reviews = db.query_one("SELECT COUNT(DISTINCT task_id) AS c FROM reviews")["c"]
    return {
        "tasks": tasks,
        "papers": papers,
        "collected": collected,
        "proposals": drafts,
        "reviews": reviews,
    }
