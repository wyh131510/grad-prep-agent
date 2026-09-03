# -*- coding: utf-8 -*-
"""设置相关接口：服务商管理、角色映射、检索参数。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import PROVIDER_PRESETS, get_settings, save_settings
from ..llm.client import LLMError, llm
from ..schemas import ProviderConfig, Settings

router = APIRouter(tags=["settings"])


class TestRequest(BaseModel):
    api_key: str = ""


class SettingsUpdate(BaseModel):
    download_dir: str | None = None
    default_provider_id: str | None = None
    role_providers: dict[str, str] | None = None
    search_options: dict | None = None


@router.get("/settings")
def read_settings() -> dict:
    return get_settings().model_dump()


@router.put("/settings")
def update_settings(body: SettingsUpdate) -> dict:
    settings: Settings = get_settings()
    if body.download_dir is not None:
        settings.download_dir = body.download_dir.strip()
    if body.default_provider_id is not None:
        settings.default_provider_id = body.default_provider_id.strip()
    if body.role_providers is not None:
        settings.role_providers = {k: v for k, v in body.role_providers.items() if v}
    if body.search_options is not None:
        opts = settings.search_options.model_dump()
        for k in ("max_results_per_source", "max_total_results", "request_timeout"):
            if k in body.search_options and body.search_options[k] is not None:
                opts[k] = int(body.search_options[k])
        settings.search_options = type(settings.search_options)(**opts)
    return save_settings(settings).model_dump()


@router.get("/settings/presets")
def presets() -> list[dict]:
    return [p.model_dump() for p in PROVIDER_PRESETS]


@router.post("/settings/providers")
def upsert_provider(body: ProviderConfig) -> dict:
    settings: Settings = get_settings()
    existing = next((p for p in settings.providers if p.id == body.id), None)
    # 编辑时 API Key 留空表示不修改已保存的 Key
    if existing and not body.api_key.strip() and existing.api_key:
        body.api_key = existing.api_key
    others = [p for p in settings.providers if p.id != body.id]
    others.append(body)
    settings.providers = others
    save_settings(settings)
    return body.model_dump()


@router.delete("/settings/providers/{provider_id}")
def delete_provider(provider_id: str) -> dict:
    settings: Settings = get_settings()
    settings.providers = [p for p in settings.providers if p.id != provider_id]
    if settings.default_provider_id == provider_id:
        settings.default_provider_id = ""
    settings.role_providers = {k: v for k, v in settings.role_providers.items() if v != provider_id}
    save_settings(settings)
    return {"ok": True}


@router.post("/settings/providers/{provider_id}/test")
def test_provider(provider_id: str, body: TestRequest) -> dict:
    settings = get_settings()
    prov = next((p for p in settings.providers if p.id == provider_id), None)
    if prov is None:
        raise HTTPException(404, f"服务商 {provider_id} 不存在")
    prov = prov.model_copy(deep=True)
    if body.api_key:
        prov.api_key = body.api_key
    if not prov.api_key:
        raise HTTPException(400, "请先填写 API Key 再测试")
    try:
        ok, message = llm.test(prov)
    except LLMError as exc:
        ok, message = False, str(exc)
    return {"ok": ok, "message": message}
