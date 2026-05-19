"""Ollama HTTP istemcisi — ince katman, sadece bizim ihtiyac duydugumuz endpoint'ler."""

from __future__ import annotations

import logging
import os
from typing import Any, AsyncIterator

import httpx

log = logging.getLogger(__name__)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=300.0, write=60.0, pool=5.0)


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, base_url: str = OLLAMA_HOST, timeout: httpx.Timeout = DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "OllamaClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    async def is_alive(self) -> bool:
        try:
            r = await self._client.get("/", timeout=httpx.Timeout(3.0))
            return r.status_code < 500
        except httpx.HTTPError:
            return False

    async def list_local(self) -> list[dict[str, Any]]:
        r = await self._client.get("/api/tags")
        r.raise_for_status()
        return list(r.json().get("models", []))

    async def list_running(self) -> list[dict[str, Any]]:
        try:
            r = await self._client.get("/api/ps")
            r.raise_for_status()
            return list(r.json().get("models", []))
        except httpx.HTTPError as exc:
            log.warning("Ollama /api/ps cagrisi basarisiz: %s", exc)
            return []

    async def pull(self, model_tag: str) -> AsyncIterator[dict[str, Any]]:
        async with self._client.stream(
            "POST",
            "/api/pull",
            json={"model": model_tag, "stream": True},
            timeout=httpx.Timeout(connect=5.0, read=None, write=60.0, pool=5.0),
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    import json
                    yield json.loads(line)
                except ValueError:
                    continue

    async def generate(
        self,
        model_tag: str,
        prompt: str,
        *,
        temperature: float | None = None,
        context_window: int | None = None,
        keep_alive: str | int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model_tag,
            "prompt": prompt,
            "stream": False,
        }
        options: dict[str, Any] = {}
        if temperature is not None:
            options["temperature"] = float(temperature)
        if context_window is not None:
            options["num_ctx"] = int(context_window)
        if options:
            payload["options"] = options
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive

        r = await self._client.post("/api/generate", json=payload)
        if r.status_code >= 400:
            raise OllamaError(f"Ollama generate hatasi {r.status_code}: {r.text[:200]}")
        return r.json()

    async def warmup(self, model_tag: str) -> None:
        try:
            await self.generate(model_tag, prompt="ping", keep_alive="10m")
        except OllamaError as exc:
            log.warning("Warmup basarisiz [%s]: %s", model_tag, exc)

    async def unload(self, model_tag: str) -> None:
        try:
            await self._client.post(
                "/api/generate",
                json={"model": model_tag, "prompt": "", "keep_alive": 0},
                timeout=httpx.Timeout(10.0),
            )
        except httpx.HTTPError as exc:
            log.warning("Unload basarisiz [%s]: %s", model_tag, exc)
