# -*- coding: utf-8 -*-
"""API 路由汇总。"""
from fastapi import APIRouter

from . import events, files, papers, proposal, review, settings, system, tasks

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(settings.router)
api_router.include_router(tasks.router)
api_router.include_router(papers.router)
api_router.include_router(proposal.router)
api_router.include_router(review.router)
api_router.include_router(events.router)
api_router.include_router(files.router)
