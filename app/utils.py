# -*- coding: utf-8 -*-
"""通用工具函数。"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

_WS_RE = re.compile(r"[ \t\u00a0]+")
_MULTI_NL_RE = re.compile(r"\n{3,}")
_TAG_RE = re.compile(r"<[^>]+>")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def make_id(*parts: str, length: int = 16) -> str:
    """由若干字段生成稳定短 id。"""
    text = "|".join(str(p) for p in parts if p)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]


def strip_html(text: str) -> str:
    return _TAG_RE.sub(" ", text or "")


def make_soup(html: str):
    """BeautifulSoup 实例：优先 lxml，未安装时降级 html.parser。"""
    from bs4 import BeautifulSoup

    try:
        return BeautifulSoup(html, "lxml")
    except Exception:  # noqa: BLE001 FeatureNotFound 等
        return BeautifulSoup(html, "html.parser")


def clean_text(text: str) -> str:
    """统一清洗：去控制符、规整空白、合并空行。"""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    text = _WS_RE.sub(" ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"(?m)^[ \t]+", "", text)
    text = _MULTI_NL_RE.sub("\n\n", text)
    return text.strip()


def truncate(text: str, limit: int = 400) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def safe_filename(name: str, max_len: int = 120) -> str:
    """生成安全的文件名（保留中文与常规字符）。"""
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", name or "file")
    name = re.sub(r"\s+", " ", name).strip(" .")
    if len(name) > max_len:
        stem, dot, ext = name.rpartition(".")
        stem = stem[: max_len - len(ext) - 1] if ext and len(ext) <= 10 else name[:max_len]
        name = f"{stem}{dot}{ext}" if ext and len(ext) <= 10 else stem
    return name or "file"


def parse_year(value: Any) -> int | None:
    """从各种来源提取年份；无效返回 None。"""
    if value is None:
        return None
    if isinstance(value, int):
        return value if 1900 <= value <= 2100 else None
    m = re.search(r"(19|20)\d{2}", str(value))
    if m:
        y = int(m.group(0))
        return y if 1900 <= y <= 2100 else None
    return None


def parse_json_lenient(text: str) -> Any:
    """宽松 JSON 解析：截取首个 {} / []，容忍尾部逗号。"""
    if text is None:
        raise ValueError("empty text")
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 截取首个完整 JSON 片段
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start >= 0:
            depth = 0
            in_str = False
            escape = False
            for i in range(start, len(text)):
                ch = text[i]
                if in_str:
                    if escape:
                        escape = False
                    elif ch == "\\":
                        escape = True
                    elif ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                elif ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
                    if depth == 0:
                        candidate = text[start : i + 1]
                        candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
                        try:
                            return json.loads(candidate)
                        except json.JSONDecodeError:
                            break
            if depth > 0:
                candidate = text[start:] + closer * depth
                candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    pass
    raise ValueError(f"无法从响应中解析 JSON: {text[:200]!r}")


def chunk_text(text: str, max_chars: int = 2400, overlap: int = 200) -> list[str]:
    """按段落把长文本切成带重叠的块，尽量不切断句子。"""
    text = clean_text(text)
    if len(text) <= max_chars:
        return [text] if text else []
    paragraphs = re.split(r"\n{2,}", text)
    chunks: list[str] = []
    buf = ""
    for para in paragraphs:
        if len(buf) + len(para) + 2 > max_chars and buf:
            chunks.append(buf)
            tail = buf[-overlap:] if overlap else ""
            buf = tail + "\n\n" + para if tail else para
        else:
            buf = f"{buf}\n\n{para}" if buf else para
    if buf:
        chunks.append(buf)
    return chunks


def rrf_fuse(rankings: Iterable[list[str]], k: int = 60) -> dict[str, float]:
    """Reciprocal Rank Fusion：融合多路排序为统一得分。"""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    if scores:
        top = max(scores.values())
        if top:
            scores = {d: s / top for d, s in scores.items()}
    return scores


def sigmoid(x: float) -> float:
    import math

    return 1.0 / (1.0 + math.exp(-x))


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def listify(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return [value]
    return [value]


def is_within(base: Path, target: Path) -> bool:
    """路径穿越防护。"""
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def start_progress_ticker(job, label: str, interval: int = 10):
    """在长耗时操作（如 LLM 生成）期间定期更新进度文案（显示已用秒数）。
    返回停止函数；调用方应在操作结束后调用停止，避免后台线程残留。
    job 需提供 .update(message=...)（线程安全）。"""
    import threading
    import time

    start = time.time()
    state = {"running": True}

    def _tick():
        while state["running"]:
            el = int(time.time() - start)
            try:
                job.update(message=f"{label}… 已用时 {el} 秒")
            except Exception:  # noqa: BLE001
                pass
            time.sleep(interval)

    t = threading.Thread(target=_tick, daemon=True)
    t.start()

    def _stop():
        state["running"] = False

    return _stop
