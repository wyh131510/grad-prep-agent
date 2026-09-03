# -*- coding: utf-8 -*-
"""本地文件预览（仅限用户指定的下载目录内，防路径穿越）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..config import get_download_dir
from ..utils import is_within

router = APIRouter(tags=["files"])


@router.get("/files/preview")
def preview(path: str) -> FileResponse:
    base = get_download_dir()
    target = (base / path).resolve()
    if not is_within(base, target) or not target.is_file():
        raise HTTPException(403, "非法路径：仅允许预览本地文献库中的文件")
    return FileResponse(target)
