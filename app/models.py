"""Pydantic veri modelleri."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(protected_namespaces=())


class LoginRequest(_Base):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)


class TokenResponse(_Base):
    access_token: str
    token_type: str = "bearer"
    department: str
    role: str
    label: str | None = None
    expires_in: int


class ChatTurn(_Base):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=8192)


class ChatRequest(_Base):
    prompt: str = Field(..., min_length=1, max_length=8192)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    model_id: str | None = None     # admin override; siradan kullanici icin yok sayilir
    history: list[ChatTurn] | None = Field(default=None, max_length=20)


class ChatResponse(_Base):
    model_id: str
    category: str
    matched_rule: str
    fallback_triggered: bool
    fallback_reason: str | None = None
    response: str
    latency_ms: float
    eval_count: int | None = None
    prompt_eval_count: int | None = None


class UserCreateRequest(_Base):
    username: str = Field(..., min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9._\-]+$")
    password: str = Field(..., min_length=6, max_length=256)
    department: str = Field(..., min_length=1, max_length=64)
    role: str = Field(default="user", pattern="^(user|admin)$")
    label: str | None = Field(default=None, max_length=128)


class UserUpdateRequest(_Base):
    department: str | None = Field(default=None, min_length=1, max_length=64)
    role: str | None = Field(default=None, pattern="^(user|admin)$")
    label: str | None = Field(default=None, max_length=128)
    new_password: str | None = Field(default=None, min_length=6, max_length=256)


class PasswordChangeRequest(_Base):
    current_password: str = Field(..., min_length=1, max_length=256)
    new_password: str = Field(..., min_length=8, max_length=256)


class ChatStreamRequest(ChatRequest):
    pass


class CatalogModelRequest(_Base):
    model_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9._\-]+$")
    ollama_tag: str = Field(..., min_length=1, max_length=128)
    category: str = Field(..., pattern="^(text|code|reasoning|persona|fallback)$")
    parameters_b: float | None = Field(default=None, ge=0.0, le=1000.0)
    ram_gb: float = Field(..., gt=0.0, le=512.0)
    vram_gb: float | None = Field(default=None, gt=0.0, le=512.0)
    profile: str | None = Field(default=None, max_length=256)


class ConfigUpdateRequest(_Base):
    profile: str | None = Field(default=None, pattern="^(auto|lite|balanced|performance)$")
    expected_users: int | None = Field(default=None, ge=1, le=1000)
    expected_concurrency: int | None = Field(default=None, ge=1, le=100)
    active_models: list[str] | None = None
    manual_override: bool | None = None
    auto_pull: bool | None = None
    idle_unload_minutes: int | None = Field(default=None, ge=1, le=1440)
    category_assignments: dict[str, list[str]] | None = None


class SystemProfileResponse(_Base):
    hardware: dict[str, Any]
    capacity: dict[str, Any]
    runtime_config: dict[str, Any]


class UsageSummary(_Base):
    username: str
    department: str
    total_requests: int
    total_tokens: int
    avg_latency_ms: float | None
    by_model: dict[str, int]
