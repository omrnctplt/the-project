"""Departman + keyword + boyut bazli routing kararlari ureten katman."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from .orchestrator import Orchestrator

log = logging.getLogger(__name__)

SIZE_THRESHOLDS = {
    "short_prompt_chars": 200,
    "long_prompt_chars": 2000,
}


@dataclass
class RoutingDecision:
    model_id: str
    category: str
    matched_rule: str
    fallback_triggered: bool = False
    fallback_reason: str | None = None
    selected_size: str | None = None     # small | medium | large

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "category": self.category,
            "matched_rule": self.matched_rule,
            "fallback_triggered": self.fallback_triggered,
            "fallback_reason": self.fallback_reason,
            "selected_size": self.selected_size,
        }


class Router:
    def __init__(
        self,
        catalog: dict[str, Any],
        orchestrator: Orchestrator,
        category_assignments: dict[str, list[str]] | None = None,
    ):
        self.catalog = catalog
        self.orchestrator = orchestrator
        rules = catalog.get("routing_rules") or []
        self._rules = sorted(rules, key=lambda r: -int(r.get("priority", 0)))
        self._departments: dict[str, dict[str, Any]] = catalog.get("departments", {}) or {}
        self._models_def: dict[str, dict[str, Any]] = catalog.get("models", {}) or {}
        # Admin kategori -> model_id atamasi (varsa kategoriyi ezer)
        self._assignments: dict[str, list[str]] = category_assignments or {}

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

    def _size_pref_for(self, department: str, prompt: str) -> str:
        """Departmanin preferred_size'i + prompt uzunlugu ile size hedefi.

        - Departmanin onerisi baz alinir.
        - Cok uzun prompt (>2000 char) varsa large'a bir tik kayar.
        - Cok kisa prompt (<200 char) ve light departman ise small'a kayar.
        """
        dept = self._department(department)
        base = str(dept.get("preferred_size", "small")).lower()
        if base not in ("small", "medium", "large"):
            base = "small"
        plen = len(prompt or "")
        order = ["small", "medium", "large"]
        idx = order.index(base)
        if plen >= SIZE_THRESHOLDS["long_prompt_chars"] and idx < 2:
            idx += 1
        elif plen <= SIZE_THRESHOLDS["short_prompt_chars"] and idx > 0 and dept.get("resource_class") == "light":
            idx -= 1
        return order[idx]

    def _model_size_b(self, model_id: str) -> float:
        m = self._models_def.get(model_id) or {}
        return float(m.get("parameters_b") or 0.0)

    def _pick_in_category_by_size(
        self,
        department: str,
        category: str,
        size_pref: str,
    ) -> str | None:
        """Bu kategorideki uygun modeller arasinda size_pref'e en yakin olani sec.

        Admin bu kategoriye model atamissa (category_assignments) yalnizca o
        modeller degerlendirilir; aksi halde modelin katalog kategorisi baz alinir.
        """
        states = self.orchestrator.states()
        assigned = self._assignments.get(category) or []

        def _match(s: dict[str, Any]) -> bool:
            return (s["model_id"] in assigned) if assigned else (s["category"] == category)

        # Once hazir olanlar (ready/loaded)
        candidates = [s for s in states if _match(s) and s["status"] in ("ready", "loaded")]
        if not candidates and getattr(self.orchestrator, "auto_pull", False):
            # Lazy pull aciksa henuz inmemis aktif modeller de aday olur;
            # kapaliyken bunlara yonlendirmek garantili 502 demek — fallback'a birak.
            candidates = [s for s in states if _match(s) and s["status"] in ("pulling", "queued", "unknown")]
        if not candidates:
            return None

        candidates.sort(
            key=lambda s: (s["inflight_requests"], self._model_size_b(s["model_id"]))
        )
        sizes = sorted({self._model_size_b(s["model_id"]) for s in candidates})
        if len(sizes) == 1:
            return candidates[0]["model_id"]

        if size_pref == "large":
            target = sizes[-1]
        elif size_pref == "medium":
            target = sizes[len(sizes) // 2]
        else:
            target = sizes[0]

        for s in candidates:
            if abs(self._model_size_b(s["model_id"]) - target) < 1e-6:
                return s["model_id"]
        return candidates[0]["model_id"]

    def decide(self, department: str, prompt: str) -> RoutingDecision:
        size_pref = self._size_pref_for(department, prompt)

        for rule in self._rules:
            when = rule.get("when") or {}
            category = None
            matched = False

            if when.get("always"):
                category = self._resolve_token(rule.get("then_category", "text"), department)
                matched = True
            else:
                pattern = when.get("prompt_matches")
                if pattern:
                    try:
                        if re.search(pattern, prompt):
                            category = self._resolve_token(rule.get("then_category", "text"), department)
                            matched = True
                    except re.error as exc:
                        log.warning("Hatali regex [%s]: %s", rule.get("name"), exc)
                        continue

            if not matched or not category:
                continue
            if not self._category_allowed(department, category):
                continue

            model_id = self._pick_in_category_by_size(department, category, size_pref)
            if model_id:
                return RoutingDecision(
                    model_id=model_id,
                    category=category,
                    matched_rule=rule.get("name", "match"),
                    selected_size=size_pref,
                )

        # Fallback
        fb = (
            self._pick_in_category_by_size(department, "fallback", "small")
            or self.orchestrator.least_busy_active("fallback")
            or self.orchestrator.least_busy_active(None)
        )
        if fb:
            state = self.orchestrator.get_state(fb)
            return RoutingDecision(
                model_id=fb,
                category=state.category if state else "fallback",
                matched_rule="fallback",
                fallback_triggered=True,
                fallback_reason="Hicbir kural eslesmedi veya hedef kategoride hazir model yok.",
                selected_size=size_pref,
            )
        raise RuntimeError("Sistemde calisir durumda hicbir model yok.")
