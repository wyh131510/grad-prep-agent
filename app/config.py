# -*- coding: utf-8 -*-
"""配置管理：设置存于 data/settings.json，进程内缓存。"""
from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

from .schemas import ProviderConfig, Settings
from .utils import ensure_dir, json_dumps

# 冻结（PyInstaller 打包）环境的路径处理：
# - APP_DIR 指向打包资源目录（web/ 被 --add-data 打包其中）
# - 数据目录放到 %LOCALAPPDATA%\GradPrepAgent（Program Files 下不可写）
_FROZEN = bool(getattr(sys, "frozen", False))
if _FROZEN:
    APP_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    _default_data = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "GradPrepAgent"
    DATA_DIR = Path(os.environ.get("GRAD_PREP_DATA_DIR") or str(_default_data))
else:
    APP_DIR = Path(__file__).resolve().parents[1]
    DATA_DIR = Path(os.environ.get("GRAD_PREP_DATA_DIR") or str(APP_DIR / "data"))
SETTINGS_PATH = DATA_DIR / "settings.json"
DB_PATH = DATA_DIR / "grad_prep.db"
FILES_DIR = DATA_DIR / "files"

_lock = threading.RLock()
_cache: Settings | None = None

# 内置服务商预设（api_key 留空，由用户填写）
PROVIDER_PRESETS: list[ProviderConfig] = [
    ProviderConfig(
        id="deepseek", name="DeepSeek", base_url="https://api.deepseek.com/v1",
        model="deepseek-chat", note="国内直连，性价比高",
    ),
    ProviderConfig(
        id="openai", name="OpenAI", base_url="https://api.openai.com/v1",
        model="gpt-4o-mini", note="需要境外网络",
    ),
    ProviderConfig(
        id="moonshot", name="Moonshot Kimi", base_url="https://api.moonshot.cn/v1",
        model="moonshot-v1-8k", note="国内直连",
    ),
    ProviderConfig(
        id="qwen", name="通义千问", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="qwen-plus", embedding_model="text-embedding-v3", note="国内直连，兼容模式",
    ),
    ProviderConfig(
        id="zhipu", name="智谱 GLM", base_url="https://open.bigmodel.cn/api/paas/v4",
        model="glm-4-flash", note="国内直连",
    ),
    ProviderConfig(
        id="siliconflow", name="硅基流动 SiliconFlow", base_url="https://api.siliconflow.cn/v1",
        model="deepseek-ai/DeepSeek-V2.5", embedding_model="BAAI/bge-m3",
        note="国内直连，聚合多家模型",
    ),
]


def default_settings() -> Settings:
    return Settings(
        download_dir=str(FILES_DIR),
        providers=[p.model_copy(deep=True) for p in PROVIDER_PRESETS],
    )


def get_settings() -> Settings:
    global _cache
    with _lock:
        if _cache is not None:
            return _cache.model_copy(deep=True)
        if SETTINGS_PATH.exists():
            try:
                _cache = Settings.model_validate_json(SETTINGS_PATH.read_text(encoding="utf-8"))
            except Exception:
                _cache = default_settings()
        else:
            _cache = default_settings()
        return _cache.model_copy(deep=True)


def save_settings(settings: Settings) -> Settings:
    global _cache
    with _lock:
        ensure_dir(DATA_DIR)
        SETTINGS_PATH.write_text(json_dumps(settings.model_dump()), encoding="utf-8")
        _cache = settings.model_copy(deep=True)
        return _cache.model_copy(deep=True)


def get_download_dir() -> Path:
    d = get_settings().download_dir or str(FILES_DIR)
    return ensure_dir(d)
