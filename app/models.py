"""Pydantic veri modelleri."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    department: str
    role: str
    label: str | None = None
    expires_in: int


class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8192)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    model_id: str | None = None     # admin override; siradan kullanici icin yok sayilir


class ChatResponse(BaseModel):
    model_id: str
    category: str
    matched_rule: str
    fallback_triggered: bool
    fallback_reason: str | None = None
    response: str
    latency_ms: float
    eval_count: int | None = None
    prompt_eval_count: int | None = None


class ConfigUpdateRequest(BaseModel):
    expected_users: int | None = Field(default=None, ge=1, le=1000)
    expected_concurrency: int | None = Field(default=None, ge=1, le=100)
    active_models: list[str] | None = None
    manual_override: bool | None = None
    auto_pull: bool | None = None
    idle_unload_minutes: int | None = Field(default=None, ge=1, le=1440)


class SystemProfileResponse(BaseModel):
    hardware: dict[str, Any]
    capacity: dict[str, Any]
    runtime_config: dict[str, Any]


class UsageSummary(BaseModel):
    username: str
    department: str
    total_requests: int
    total_tokens: int
    avg_latency_ms: float | None
    by_model: dict[str, int]
