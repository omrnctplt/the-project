"""Sohbet — one-shot ve streaming. Rate limit + routing karari tek yerde."""

from __future__ import annotations

import json as _json
import time
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from .. import audit, auth, metrics, usage
from ..deps import get_state
from ..models import ChatRequest, ChatResponse, ChatStreamRequest
from ..ollama_client import OllamaError
from ..state import AppState

router = APIRouter()


@dataclass
class ChatDecision:
    model_id: str
    category: str
    matched_rule: str
    fallback: bool
    fallback_reason: str | None


HISTORY_MAX_TURNS = 8
HISTORY_MAX_CHARS = 6000


def _resolve_rate_limit(catalog: dict[str, Any], department: str) -> int:
    dept = (catalog.get("departments") or {}).get(department) or {}
    return int(dept.get("rate_limit_per_min", 30))


def _compose_prompt(body: ChatRequest) -> str:
    """Cok turlu sohbet: onceki turlari karakter butcesiyle prompt'a gomer.

    Routing karari ve audit ham `body.prompt` uzerinden yapilir; gecmis
    yalnizca modele giden metne eklenir (sunucuda saklanmaz).
    """
    if not body.history:
        return body.prompt
    turns = body.history[-HISTORY_MAX_TURNS:]
    parts: list[str] = []
    used = 0
    for t in reversed(turns):
        chunk = f"{'Kullanici' if t.role == 'user' else 'Asistan'}: {t.content}"
        if used + len(chunk) > HISTORY_MAX_CHARS:
            break
        parts.append(chunk)
        used += len(chunk)
    if not parts:
        return body.prompt
    history_text = "\n\n".join(reversed(parts))
    return (
        "Asagida ayni kullaniciyla onceki konusma var. Baglami dikkate alarak son mesaja yanit ver.\n\n"
        f"{history_text}\n\nKullanici: {body.prompt}\nAsistan:"
    )


def _enforce_ready_and_rate(state: AppState, principal: dict[str, Any]) -> None:
    if not state.ready or not state.router or not state.orchestrator:
        raise HTTPException(status_code=503, detail="Gateway henuz hazir degil")
    department = principal["department"]
    rate_limit = _resolve_rate_limit(state.catalog, department)
    allowed, _count = usage.check_and_record_rate(
        key=f"user:{principal['username']}", limit_per_min=rate_limit
    )
    if not allowed:
        metrics.RATE_LIMITED.labels(department=department).inc()
        raise HTTPException(
            status_code=429,
            detail=f"Departman/kullanici dakika basina {rate_limit} istek limitini asti",
            headers={"Retry-After": "60"},
        )


def _decide(state: AppState, principal: dict[str, Any], prompt: str, model_id: str | None) -> ChatDecision:
    if model_id and principal["role"] == "admin":
        override = state.orchestrator.get_state(model_id)
        if not override:
            raise HTTPException(status_code=400, detail=f"Model bulunamadi: {model_id}")
        return ChatDecision(
            model_id=model_id,
            category=override.category,
            matched_rule="admin_override",
            fallback=False,
            fallback_reason=None,
        )
    try:
        decision = state.router.decide(principal["department"], prompt)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Henuz hazir model yok: {exc}. Modeller indiriliyor olabilir veya Ollama erisilemez.",
        ) from exc
    if decision.fallback_triggered:
        metrics.FALLBACKS.labels(department=principal["department"]).inc()
    return ChatDecision(
        model_id=decision.model_id,
        category=decision.category,
        matched_rule=decision.matched_rule,
        fallback=decision.fallback_triggered,
        fallback_reason=decision.fallback_reason,
    )


@router.post("/api/v1/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    request: Request,
    principal: dict[str, Any] = Depends(auth.current_principal),
) -> ChatResponse:
    state = get_state(request)
    _enforce_ready_and_rate(state, principal)
    department = principal["department"]
    username = principal["username"]
    d = _decide(state, principal, body.prompt, body.model_id)

    metrics.INFLIGHT.inc()
    try:
        try:
            with metrics.LATENCY.labels(model=d.model_id, category=d.category).time():
                result = await state.orchestrator.call(
                    d.model_id,
                    _compose_prompt(body),
                    temperature=body.temperature,
                    context_window=state.catalog.get("defaults", {}).get("context_window"),
                )
        except OllamaError as exc:
            metrics.REQUESTS.labels(
                model=d.model_id, category=d.category,
                department=department, status="error",
            ).inc()
            audit.write(
                username=username, department=department, prompt=body.prompt,
                model_id=d.model_id, category=d.category, matched_rule=d.matched_rule,
                fallback=d.fallback, status="error", latency_ms=None, error=str(exc),
            )
            raise HTTPException(status_code=502, detail=f"Model hatasi: {exc}") from exc

        response_text = str(result.get("response") or "")
        latency_ms = float(result.get("_latency_ms") or 0.0)
        eval_count = int(result.get("eval_count") or 0)
        prompt_eval_count = int(result.get("prompt_eval_count") or 0)

        metrics.REQUESTS.labels(
            model=d.model_id, category=d.category,
            department=department, status="ok",
        ).inc()
        metrics.TOKENS_OUT.labels(model=d.model_id).inc(eval_count)

        usage.record(
            username=username, model_id=d.model_id,
            tokens_in=prompt_eval_count, tokens_out=eval_count,
            latency_ms=latency_ms,
        )
        audit.write(
            username=username, department=department, prompt=body.prompt,
            model_id=d.model_id, category=d.category, matched_rule=d.matched_rule,
            fallback=d.fallback, status="ok", latency_ms=latency_ms,
            tokens_in=prompt_eval_count, tokens_out=eval_count,
        )

        return ChatResponse(
            model_id=d.model_id,
            category=d.category,
            matched_rule=d.matched_rule,
            fallback_triggered=d.fallback,
            fallback_reason=d.fallback_reason,
            response=response_text,
            latency_ms=latency_ms,
            eval_count=eval_count,
            prompt_eval_count=prompt_eval_count,
        )
    finally:
        metrics.INFLIGHT.dec()


@router.post("/api/v1/chat/stream")
async def chat_stream(
    body: ChatStreamRequest,
    request: Request,
    principal: dict[str, Any] = Depends(auth.current_principal),
) -> StreamingResponse:
    state = get_state(request)
    _enforce_ready_and_rate(state, principal)
    department = principal["department"]
    username = principal["username"]
    d = _decide(state, principal, body.prompt, body.model_id)

    async def event_source():
        metrics.INFLIGHT.inc()
        header = {
            "event": "start",
            "model_id": d.model_id,
            "category": d.category,
            "matched_rule": d.matched_rule,
            "fallback_triggered": d.fallback,
            "fallback_reason": d.fallback_reason,
        }
        yield _json.dumps(header, ensure_ascii=False) + "\n"
        total_eval = 0
        total_prompt_eval = 0
        latency_ms = 0.0
        status = "ok"
        t0 = time.perf_counter()
        try:
            with metrics.LATENCY.labels(model=d.model_id, category=d.category).time():
                async for event in state.orchestrator.call_stream(  # type: ignore[union-attr]
                    d.model_id,
                    _compose_prompt(body),
                    temperature=body.temperature,
                    context_window=state.catalog.get("defaults", {}).get("context_window"),
                ):
                    if "_pull_progress" in event:
                        pp = event["_pull_progress"] or {}
                        yield _json.dumps({
                            "event": "status",
                            "stage": "pull",
                            "model_id": d.model_id,
                            "status": pp.get("status"),
                            "progress": pp.get("pull_progress"),
                            "stage_text": pp.get("pull_stage"),
                            "completed_mb": pp.get("pull_completed_mb"),
                            "total_mb": pp.get("pull_total_mb"),
                            "speed_mbps": pp.get("pull_speed_mbps"),
                            "eta_seconds": pp.get("pull_eta_seconds"),
                        }, ensure_ascii=False) + "\n"
                        continue
                    if event.get("eval_count"):
                        total_eval = int(event["eval_count"])
                    if event.get("prompt_eval_count"):
                        total_prompt_eval = int(event["prompt_eval_count"])
                    out = {
                        "event": "token",
                        "response": event.get("response", ""),
                        "done": bool(event.get("done", False)),
                    }
                    if event.get("done"):
                        out["eval_count"] = total_eval
                        out["prompt_eval_count"] = total_prompt_eval
                    yield _json.dumps(out, ensure_ascii=False) + "\n"
            metrics.REQUESTS.labels(
                model=d.model_id, category=d.category,
                department=department, status="ok",
            ).inc()
            metrics.TOKENS_OUT.labels(model=d.model_id).inc(total_eval)
        except Exception as exc:
            status = "error"
            metrics.REQUESTS.labels(
                model=d.model_id, category=d.category,
                department=department, status="error",
            ).inc()
            err = {"event": "error", "detail": str(exc)}
            yield _json.dumps(err, ensure_ascii=False) + "\n"
        finally:
            latency_ms = (time.perf_counter() - t0) * 1000
            metrics.INFLIGHT.dec()
            usage.record(
                username=username, model_id=d.model_id,
                tokens_in=total_prompt_eval, tokens_out=total_eval,
                latency_ms=latency_ms,
            )
            audit.write(
                username=username, department=department, prompt=body.prompt,
                model_id=d.model_id, category=d.category, matched_rule=d.matched_rule,
                fallback=d.fallback, status=status, latency_ms=latency_ms,
                tokens_in=total_prompt_eval, tokens_out=total_eval,
            )

    return StreamingResponse(event_source(), media_type="application/x-ndjson")
