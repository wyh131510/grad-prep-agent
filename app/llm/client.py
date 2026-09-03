# -*- coding: utf-8 -*-
"""统一 LLM 客户端：支持任意 OpenAI 兼容服务商，按角色路由，结构化 JSON 输出。"""
from __future__ import annotations

from typing import Any, Iterable

from openai import OpenAI

from ..config import get_settings
from ..schemas import ProviderConfig
from ..utils import parse_json_lenient
from .prompts import rerank_prompt


class LLMError(RuntimeError):
    """LLM 调用失败（未配置 / 网络 / 协议不支持等）。"""


class LLM:
    # ------------------------------------------------------------ 服务商解析
    def resolve(self, role: str = "") -> ProviderConfig:
        """按角色解析服务商（公开接口）。"""
        return self._resolve(role)

    def _resolve(self, role: str = "") -> ProviderConfig:
        settings = get_settings()
        # 仅启用且已填写 API Key 的服务商视为可用
        providers = [p for p in settings.providers if p.enabled and p.api_key.strip()]
        if not providers:
            raise LLMError("尚未配置可用的大模型服务商：请到「设置」页添加服务商并填写 API Key")
        pid = (settings.role_providers or {}).get(role) or settings.default_provider_id
        if pid:
            for p in providers:
                if p.id == pid:
                    return p
        return providers[0]

    def _resolve_by_id(self, provider_id: str) -> ProviderConfig:
        settings = get_settings()
        for p in settings.providers:
            if p.id == provider_id:
                return p
        raise LLMError(f"服务商 {provider_id} 不存在")

    @staticmethod
    def _client(prov: ProviderConfig) -> OpenAI:
        return OpenAI(
            api_key=prov.api_key or "EMPTY",
            base_url=prov.base_url.rstrip("/"),
            timeout=180.0,  # 单次调用超时（过长会挂起）；配合 _chat 重试，避免无限等待
            max_retries=1,
        )

    # ------------------------------------------------------------ 对话
    def _chat(self, prov: ProviderConfig, messages: list[dict], **kw: Any) -> str:
        client = self._client(prov)
        last_err = ""
        for attempt in range(3):  # 网络抖动/偶发空回复：自动重试
            try:
                resp = client.chat.completions.create(
                    model=kw.pop("model", None) or prov.model or "default",
                    messages=messages,
                    temperature=kw.pop("temperature", 0.3),
                    max_tokens=kw.pop("max_tokens", 4096),
                    **kw,
                )
            except Exception as exc:  # noqa: BLE001
                last_err = f"{prov.name}（{prov.base_url}）失败：{exc}"
                if attempt < 2:
                    import time

                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise LLMError(last_err) from exc
            content = (resp.choices[0].message.content or "").strip() if resp.choices else ""
            if content:
                return content
            last_err = f"{prov.name} 返回了空内容"
            if attempt < 2:
                import time

                time.sleep(1.5 * (attempt + 1))
        raise LLMError(f"{last_err}（已自动重试 3 次）")

    def chat(
        self,
        role: str = "",
        messages: list[dict] | None = None,
        *,
        provider_id: str = "",
        model: str | None = None,
        temperature: float = 0.3,
        json_mode: bool = False,
        max_tokens: int = 4096,
    ) -> str:
        """按角色（或显式 provider_id）调用对话模型。"""
        if messages is None:
            messages = []
        prov = self._resolve_by_id(provider_id) if provider_id else self._resolve(role)
        kwargs: dict[str, Any] = dict(temperature=temperature, max_tokens=max_tokens)
        if model:
            kwargs["model"] = model
        if json_mode:
            try:
                kwargs["response_format"] = {"type": "json_object"}
                return self._chat(prov, messages, **kwargs)
            except LLMError:
                # 部分兼容端点不支持 response_format：去掉后重试一次
                kwargs.pop("response_format", None)
                return self._chat(prov, messages, **kwargs)
        return self._chat(prov, messages, **kwargs)

    def chat_json(self, role: str = "", messages: list[dict] | None = None, **kw: Any) -> Any:
        text = self.chat(role, messages, json_mode=True, **kw)
        try:
            return parse_json_lenient(text)
        except ValueError as exc:
            raise LLMError(f"模型未按 JSON 格式输出：{exc}") from exc

    # ------------------------------------------------------------ 嵌入
    def embed(self, texts: Iterable[str], role: str = "", provider_id: str = "") -> list[list[float]]:
        prov = self._resolve_by_id(provider_id) if provider_id else self._resolve(role)
        model = prov.embedding_model or ""
        if not model:
            raise LLMError(f"{prov.name} 未配置 embedding 模型名（embedding_model）")
        client = self._client(prov)
        try:
            resp = client.embeddings.create(model=model, input=list(texts))
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"{prov.name} 嵌入调用失败：{exc}") from exc
        return [d.embedding for d in resp.data]

    # ------------------------------------------------------------ 精排兜底
    def rerank_fallback(self, query: str, docs: list[dict], role: str = "", provider_id: str = "") -> list[float]:
        """LLM 逐篇相关性打分（0~1）。docs: [{id,title,abstract}]。
        服务商未配置时直接抛 LLMError（由调用方整体跳过精排），
        单篇调用失败时给中性分 0.5，避免个别篇目拖垮排序。"""
        self._resolve_by_id(provider_id) if provider_id else self._resolve(role)
        scores: list[float] = []
        for doc in docs[:40]:
            try:
                data = self.chat_json(
                    role,
                    [
                        {
                            "role": "user",
                            "content": rerank_prompt(
                                query, doc.get("title", ""), doc.get("abstract", "")
                            ),
                        }
                    ],
                    provider_id=provider_id,
                    temperature=0.0,
                )
                s = float(data.get("score", 50)) / 100.0
                scores.append(max(0.0, min(1.0, s)))
            except LLMError:
                scores.append(0.5)
        return scores

    # ------------------------------------------------------------ 连通性测试
    def test(self, prov: ProviderConfig) -> tuple[bool, str]:
        client = self._client(prov)
        try:
            resp = client.chat.completions.create(
                model=prov.model or "default",
                messages=[{"role": "user", "content": "请只回复两个字：正常"}],
                temperature=0.0,
                max_tokens=16,
            )
            content = (resp.choices[0].message.content or "").strip()
            return True, f"连接成功，模型「{prov.model}」响应：{content[:50]}"
        except Exception as exc:  # noqa: BLE001
            return False, f"连接失败：{exc}"


llm = LLM()
