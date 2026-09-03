# -*- coding: utf-8 -*-
"""全局数据模型（API 契约的代码化）。"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------- 设置


class ProviderConfig(BaseModel):
    id: str
    name: str
    base_url: str
    api_key: str = ""
    model: str = ""
    embedding_model: str = ""
    enabled: bool = True
    note: str = ""


class SearchOptions(BaseModel):
    max_results_per_source: int = 10
    max_total_results: int = 80
    request_timeout: int = 30
    # 抓取策略：source 原生接口优先；direct_url 抓取完整 HTML
    fetch_fulltext_on_collect: bool = True


class Settings(BaseModel):
    download_dir: str = ""
    default_provider_id: str = ""
    role_providers: dict[str, str] = Field(default_factory=dict)
    search_options: SearchOptions = Field(default_factory=SearchOptions)
    providers: list[ProviderConfig] = Field(default_factory=list)


# ---------------------------------------------------------------- 任务与检索


class TaskCreate(BaseModel):
    topic: str
    major: str = ""
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    sources: list[str] = Field(default_factory=list)
    requirements: str = ""
    urls: list[str] = Field(default_factory=list)  # 可选：用户提供的文献直链列表


class TaskUpdate(BaseModel):
    """任务参数编辑（选题/年份/来源等均可改）。"""

    topic: Optional[str] = None
    major: Optional[str] = None
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    sources: Optional[list[str]] = None
    requirements: Optional[str] = None
    urls: Optional[list[str]] = None


class Task(BaseModel):
    id: str
    topic: str
    major: str = ""
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    sources: list[str] = Field(default_factory=list)
    requirements: str = ""
    urls: list[str] = Field(default_factory=list)
    feedback: str = ""
    status: str = "created"
    plan: Optional[dict] = None
    paper_count: int = 0
    collected_count: int = 0
    created_at: str = ""
    updated_at: str = ""


class PlanQuery(BaseModel):
    text: str
    lang: str = "zh"  # zh | en


class PlanSubQuestion(BaseModel):
    question: str
    rationale: str = ""
    queries: list[PlanQuery] = Field(default_factory=list)


class TopicPlan(BaseModel):
    sub_questions: list[PlanSubQuestion] = Field(default_factory=list)


# ---------------------------------------------------------------- 文献


class Snippet(BaseModel):
    text: str
    section: str = ""
    page: Optional[int] = None


class Figure(BaseModel):
    caption: str = ""
    description: str = ""
    page: Optional[int] = None
    image: str = ""  # 相对 download_dir 的图片路径


class PaperSummary(BaseModel):
    research_question: str = ""
    method: str = ""
    contributions: list[str] = Field(default_factory=list)
    dataset: str = ""
    metrics: str = ""
    limitations: str = ""
    relevance_to_topic: str = ""
    key_points: list[str] = Field(default_factory=list)
    language: str = "zh"


class TranslationResult(BaseModel):
    title_zh: str = ""
    abstract_zh: str = ""
    snippets_zh: list[str] = Field(default_factory=list)  # 关键片段译文（与 paper.snippets 前 5 条对应）
    glossary: dict[str, str] = Field(default_factory=dict)
    quality_note: str = ""


class Paper(BaseModel):
    id: str
    task_id: str
    title: str
    title_zh: str = ""
    authors: list[str] = Field(default_factory=list)
    year: Optional[int] = None
    venue: str = ""
    source: str = ""
    doi: str = ""
    arxiv_id: str = ""
    url: str = ""
    pdf_url: str = ""
    abstract: str = ""
    abstract_zh: str = ""
    keywords: list[str] = Field(default_factory=list)
    citations: Optional[int] = None
    is_open_access: bool = False
    snippets: list[Snippet] = Field(default_factory=list)
    figures: list[Figure] = Field(default_factory=list)
    score: float = 0.0
    bm25_score: float = 0.0
    vector_score: float = 0.0
    rerank_score: float = 0.0
    collected: bool = False
    file_path: str = ""
    download_status: str = "none"  # none | downloading | done | failed
    download_note: str = ""
    summary: Optional[PaperSummary] = None
    translation: Optional[TranslationResult] = None
    created_at: str = ""


# ---------------------------------------------------------------- 开题报告


class ProposalSection(BaseModel):
    key: str
    title: str
    content: str = ""
    status: str = "empty"  # empty | draft | edited
    updated_at: str = ""


class TemplateInfo(BaseModel):
    filename: str = ""
    content_md: str = ""
    sections: list[str] = Field(default_factory=list)  # 检测到的分块 key


# ---------------------------------------------------------------- 评审与答辩


class ReviewIssue(BaseModel):
    severity: str = "medium"  # high | medium | low
    section: str = ""
    problem: str = ""
    suggestion: str = ""
    evidence: str = ""
    applied: bool = False  # 是否已通过「辅助修改」处理过


class ReviewResult(BaseModel):
    agent: str  # academic | logic | feasibility | format
    agent_name: str = ""
    provider_id: str = ""
    model: str = ""
    score: int = 0
    summary: str = ""
    issues: list[ReviewIssue] = Field(default_factory=list)


class ConflictItem(BaseModel):
    topic: str = ""
    opinions: list[str] = Field(default_factory=list)
    resolution: str = ""


class Suggestion(BaseModel):
    priority: int = 1
    section: str = ""
    action: str = ""
    reason: str = ""
    applied: bool = False  # 是否已通过「辅助修改」处理过


class MergedReview(BaseModel):
    overall_score: int = 0
    verdict: str = ""
    conflicts: list[ConflictItem] = Field(default_factory=list)
    final_suggestions: list[Suggestion] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- Job


class JobSnapshot(BaseModel):
    id: str
    type: str
    label: str
    status: str  # running | done | error
    progress: float = 0.0
    message: str = ""
    result: Any = None
    error: Optional[str] = None
