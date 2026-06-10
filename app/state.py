"""Calisma zamanindaki paylasilan durum (orchestrator, router, capacity, hw, bootstrap)."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from .orchestrator import Orchestrator
from .router import Router


@dataclass
class BootstrapStep:
    key: str
    label: str
    status: str = "pending"      # pending | running | ok | warn | error | skipped
    detail: str | None = None
    started_at: float | None = None
    finished_at: float | None = None

    @property
    def elapsed_ms(self) -> int | None:
        if self.started_at is None:
            return None
        end = self.finished_at if self.finished_at else time.time()
        return int((end - self.started_at) * 1000)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "status": self.status,
            "detail": self.detail,
            "elapsed_ms": self.elapsed_ms,
        }


@dataclass
class BootstrapTracker:
    steps: list[BootstrapStep] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    def add(self, key: str, label: str) -> BootstrapStep:
        step = BootstrapStep(key=key, label=label)
        self.steps.append(step)
        return step

    def get(self, key: str) -> BootstrapStep | None:
        return next((s for s in self.steps if s.key == key), None)

    def start(self, key: str, detail: str | None = None) -> BootstrapStep:
        step = self.get(key) or self.add(key, key)
        step.status = "running"
        step.detail = detail
        step.started_at = time.time()
        return step

    def finish(self, key: str, status: str = "ok", detail: str | None = None) -> None:
        step = self.get(key)
        if not step:
            step = self.add(key, key)
            step.started_at = time.time()
        step.status = status
        if detail is not None:
            step.detail = detail
        step.finished_at = time.time()

    def overall_status(self) -> str:
        if any(s.status == "error" for s in self.steps):
            return "error"
        if any(s.status == "running" for s in self.steps):
            return "running"
        if any(s.status == "pending" for s in self.steps):
            return "pending"
        if any(s.status == "warn" for s in self.steps):
            return "warn"
        return "ok"

    def to_dict(self) -> dict[str, Any]:
        end = self.finished_at if self.finished_at else time.time()
        return {
            "overall_status": self.overall_status(),
            "started_at": self.started_at,
            "elapsed_ms": int((end - self.started_at) * 1000),
            "steps": [s.to_dict() for s in self.steps],
        }


@dataclass
class AppState:
    hw_profile: dict[str, Any] = field(default_factory=dict)
    capacity: dict[str, Any] = field(default_factory=dict)
    runtime_config: dict[str, Any] = field(default_factory=dict)
    catalog: dict[str, Any] = field(default_factory=dict)
    orchestrator: Orchestrator | None = None
    router: Router | None = None
    ready: bool = False
    tasks: list[asyncio.Task] = field(default_factory=list)
    sweep_task: asyncio.Task | None = None
    bootstrap: BootstrapTracker = field(default_factory=BootstrapTracker)
