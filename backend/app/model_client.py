from __future__ import annotations

import json
import time
from typing import Any

import httpx

from .config import AppConfig


class ModelError(RuntimeError):
    pass


class OpenAICompatibleModel:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1200,
    ) -> str:
        headers = {"Content-Type": "application/json"}
        if self.config.model_api_key:
            headers["Authorization"] = f"Bearer {self.config.model_api_key}"

        payload: dict[str, Any] = {
            "model": self.config.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            async with httpx.AsyncClient(timeout=self.config.model_timeout_seconds) as client:
                response = await client.post(
                    f"{self.config.model_base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ModelError(str(exc) or f"Timed out after {self.config.model_timeout_seconds:g}s.") from exc
        except httpx.HTTPError as exc:
            raise ModelError(str(exc) or exc.__class__.__name__) from exc

        data = response.json()
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelError(f"Unexpected model response: {json.dumps(data)[:500]}") from exc

    async def health_check(self, *, timeout_seconds: float = 8.0) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.config.model_api_key:
            headers["Authorization"] = f"Bearer {self.config.model_api_key}"

        endpoint = f"{self.config.model_base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.config.model_name,
            "messages": [
                {"role": "system", "content": "Reply with OK only."},
                {"role": "user", "content": "health check"},
            ],
            "temperature": 0,
            "max_tokens": 8,
        }
        started = time.perf_counter()
        base: dict[str, Any] = {
            "model": self.config.model_name,
            "base_url": self.config.model_base_url,
            "endpoint": endpoint,
            "timeout_seconds": timeout_seconds,
        }

        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(endpoint, headers=headers, json=payload)
                response.raise_for_status()
            data = response.json()
            content = str(data["choices"][0]["message"]["content"])
            return {
                **base,
                "ok": True,
                "status": "ok",
                "latency_ms": round((time.perf_counter() - started) * 1000),
                "response_excerpt": content.strip()[:80],
                "error": "",
            }
        except httpx.TimeoutException as exc:
            return {
                **base,
                "ok": False,
                "status": "timeout",
                "latency_ms": round((time.perf_counter() - started) * 1000),
                "response_excerpt": "",
                "error": str(exc)[:240] or f"Timed out after {timeout_seconds:g}s.",
            }
        except httpx.HTTPStatusError as exc:
            return {
                **base,
                "ok": False,
                "status": "error",
                "latency_ms": round((time.perf_counter() - started) * 1000),
                "response_excerpt": "",
                "error": f"{exc.response.status_code} {exc.response.text[:220]}",
            }
        except (httpx.HTTPError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            return {
                **base,
                "ok": False,
                "status": "error",
                "latency_ms": round((time.perf_counter() - started) * 1000),
                "response_excerpt": "",
                "error": str(exc)[:240],
            }
