# -*- coding: utf-8 -*-
"""SQLite 薄封装（线程安全，WAL 模式）。"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    major TEXT DEFAULT '',
    year_from INTEGER,
    year_to INTEGER,
    sources TEXT DEFAULT '[]',
    requirements TEXT DEFAULT '',
    feedback TEXT DEFAULT '',
    urls TEXT DEFAULT '[]',
    status TEXT DEFAULT 'created',
    plan TEXT,
    created_at TEXT DEFAULT '',
    updated_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    title TEXT NOT NULL,
    title_zh TEXT DEFAULT '',
    authors TEXT DEFAULT '[]',
    year INTEGER,
    venue TEXT DEFAULT '',
    source TEXT DEFAULT '',
    doi TEXT DEFAULT '',
    arxiv_id TEXT DEFAULT '',
    url TEXT DEFAULT '',
    pdf_url TEXT DEFAULT '',
    abstract TEXT DEFAULT '',
    abstract_zh TEXT DEFAULT '',
    keywords TEXT DEFAULT '[]',
    citations INTEGER,
    is_open_access INTEGER DEFAULT 0,
    snippets TEXT DEFAULT '[]',
    figures TEXT DEFAULT '[]',
    score REAL DEFAULT 0,
    bm25_score REAL DEFAULT 0,
    vector_score REAL DEFAULT 0,
    rerank_score REAL DEFAULT 0,
    collected INTEGER DEFAULT 0,
    file_path TEXT DEFAULT '',
    download_status TEXT DEFAULT 'none',
    download_note TEXT DEFAULT '',
    summary TEXT,
    translation TEXT,
    created_at TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_papers_task ON papers(task_id);
CREATE INDEX IF NOT EXISTS idx_papers_collected ON papers(collected);

CREATE TABLE IF NOT EXISTS proposals (
    task_id TEXT NOT NULL,
    key TEXT NOT NULL,
    title TEXT DEFAULT '',
    content TEXT DEFAULT '',
    status TEXT DEFAULT 'empty',
    updated_at TEXT DEFAULT '',
    PRIMARY KEY (task_id, key)
);

CREATE TABLE IF NOT EXISTS reviews (
    task_id TEXT NOT NULL,
    agent TEXT NOT NULL,
    result TEXT DEFAULT '{}',
    created_at TEXT DEFAULT '',
    PRIMARY KEY (task_id, agent)
);

CREATE TABLE IF NOT EXISTS defense (
    task_id TEXT PRIMARY KEY,
    content TEXT DEFAULT '',
    created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS templates (
    task_id TEXT PRIMARY KEY,
    filename TEXT DEFAULT '',
    content_md TEXT DEFAULT '',
    sections TEXT DEFAULT '[]',
    uploaded_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS surveys (
    task_id TEXT PRIMARY KEY,
    content TEXT DEFAULT '',
    clusters TEXT DEFAULT '[]',
    paper_ids TEXT DEFAULT '[]',
    created_at TEXT DEFAULT ''
);
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(SCHEMA)
            self._migrate()
            self._conn.commit()

    def _migrate(self) -> None:
        """为已存在的库补充新列（CREATE TABLE IF NOT EXISTS 不会改动旧表）。"""
        for col, ddl in (
            ("download_status", "ALTER TABLE papers ADD COLUMN download_status TEXT DEFAULT 'none'"),
            ("download_note", "ALTER TABLE papers ADD COLUMN download_note TEXT DEFAULT ''"),
        ):
            try:
                self._conn.execute(ddl)
            except sqlite3.OperationalError:
                pass  # 列已存在

    # ---------- 基础 ----------
    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            self._conn.commit()
            return cur

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            return [dict(r) for r in cur.fetchall()]

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> dict | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    # ---------- 通用 upsert ----------
    def upsert(self, table: str, data: dict, conflict_cols: list[str], update_cols: list[str] | None = None) -> None:
        cols = list(data.keys())
        placeholders = ", ".join("?" for _ in cols)
        updates = ", ".join(f"{c}=excluded.{c}" for c in (update_cols or [c for c in cols if c not in conflict_cols]))
        conflict = ", ".join(conflict_cols)
        sql = (
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT({conflict}) DO UPDATE SET {updates}"
        )
        self.execute(sql, [data[c] for c in cols])

    def close(self) -> None:
        with self._lock:
            self._conn.close()


from .config import DB_PATH  # noqa: E402

db = Database(DB_PATH)
