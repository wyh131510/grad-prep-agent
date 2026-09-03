# -*- coding: utf-8 -*-
"""FastAPI 主程序。"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api import api_router
from .config import APP_DIR

WEB_DIR = Path(APP_DIR) / "web"

app = FastAPI(title="毕业设计前期准备 Agent", version=__version__, docs_url="/api/docs")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)
app.include_router(api_router, prefix="/api")

# 前端静态文件挂到根路径（index.html 内用相对路径引用 style.css/app.js 等）；
# /api 路由已先注册，优先匹配，不会被静态挂载遮蔽。
if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
