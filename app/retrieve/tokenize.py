# -*- coding: utf-8 -*-
"""分词：英文按词，中文优先 jieba，未安装时退化为双字滑窗。"""
from __future__ import annotations

import re

try:
    import jieba  # type: ignore

    _JIEBA = True
except ImportError:  # pragma: no cover
    _JIEBA = False

_WORD = re.compile(r"[a-z0-9][a-z0-9\-\.\+]*")
_ZH = re.compile(r"[\u4e00-\u9fff]+")


def tokenize(text: str) -> list[str]:
    text = (text or "").lower()
    tokens = _WORD.findall(text)
    for seg in _ZH.findall(text):
        if _JIEBA:
            tokens.extend(t for t in jieba.cut(seg) if t.strip())
        else:
            tokens.extend(seg[i : i + 2] for i in range(len(seg) - 1))
            if len(seg) == 1:
                tokens.append(seg)
    return [t for t in tokens if len(t) > 1 or t.isdigit()]


def jieba_available() -> bool:
    return _JIEBA
