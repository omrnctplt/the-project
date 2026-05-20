"""Calisma zamanindaki paylasilan durum (orchestrator, router, capacity, hw)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from .orchestrator import Orchestrator
from .router import Router


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
