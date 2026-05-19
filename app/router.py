"""Departman + keyword tabanli routing kararlarini ureten katman."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from .orchestrator import Orchestrator

log = logging.getLogger(__name__)


@dataclass
class RoutingDecision:
    model_id: str
    category: str
    matched_rule: str
    fallback_triggered: bool = False
    fallback_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "category": self.category,
            "matched_rule": self.matched_rule,
            "fallback_triggered": self.fallback_triggered,
            "fallback_reason": self.fallback_reason,
        }


class Router:
    def __init__(self, catalog: dict[str, Any], orchestrator: Orchestrator):
        self.catalog = catalog
        self.orchestrator = orchestrator
        rules = catalog.get("routing_rules") or []
        self._rules = sorted(rules, key=lambda r: -int(r.get("priority", 0)))
        self._departments: dict[str, dict[str, Any]] = catalog.get("departments", {}) or {}

    def _department(self, department: str) -> dict[str, Any]:
        return self._departments.get(department) or self._departments.get("general") or {}

    def _resolve_token(self, token: str, department: str) -> str:
        if token == "@department_primary":
            return str(self._department(department).get("primary_category", "text"))
        return token

    def _category_allowed(self, department: str, category: str) -> bool:
        allowed = self._department(department).get("allowed_categories")
        if not allowed:
            return True
        return category in allowed

    def _pick_model_for_category(self, department: str, category: str) -> str | None:
        chosen = self.orchestrator.first_ready(category)
        if chosen:
            return chosen
        chosen = self.orchestrator.least_busy_active(category)
        return chosen

    def decide(self, department: str, prompt: str) -> RoutingDecision:
        for rule in self._rules:
            when = rule.get("when") or {}
            if when.get("always"):
                category = self._resolve_token(rule.get("then_category", "text"), department)
                if not self._category_allowed(department, category):
                    continue
                model_id = self._pick_model_for_category(department, category)
                if model_id:
                    return RoutingDecision(model_id, category, rule.get("name", "always"))
                continue

            pattern = when.get("prompt_matches")
            if pattern:
                try:
                    if not re.search(pattern, prompt):
                        continue
                except re.error as exc:
                    log.warning("Hatali regex [%s]: %s", rule.get("name"), exc)
                    continue
                category = self._resolve_token(rule.get("then_category", "text"), department)
                if not self._category_allowed(department, category):
                    continue
                model_id = self._pick_model_for_category(department, category)
                if model_id:
                    return RoutingDecision(model_id, category, rule.get("name", "match"))

        fallback_model = (
            self.orchestrator.first_ready("fallback")
            or self.orchestrator.least_busy_active("fallback")
            or self.orchestrator.least_busy_active(None)
        )
        if fallback_model:
            state = self.orchestrator.get_state(fallback_model)
            return RoutingDecision(
                model_id=fallback_model,
                category=state.category if state else "fallback",
                matched_rule="fallback",
                fallback_triggered=True,
                fallback_reason="Hicbir kural eslesmedi veya hedef kategoride hazir model yok.",
            )
        raise RuntimeError("Sistemde calisir durumda hicbir model yok.")
