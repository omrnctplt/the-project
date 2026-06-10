"""Router karar mantigi testleri."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.orchestrator import ModelState, Orchestrator
from app.router import Router


CATALOG = {
    "models": {
        "txt-1": {"ollama_tag": "txt:1", "category": "text"},
        "code-1": {"ollama_tag": "code:1", "category": "code"},
        "reason-1": {"ollama_tag": "reason:1", "category": "reasoning"},
        "fb": {"ollama_tag": "fb:1", "category": "fallback"},
    },
    "departments": {
        "hr": {"primary_category": "text", "allowed_categories": ["text", "fallback"]},
        "engineering": {"primary_category": "code", "allowed_categories": ["code", "text", "reasoning", "fallback"]},
        "finance": {"primary_category": "reasoning", "allowed_categories": ["reasoning", "text", "fallback"]},
        "general": {"primary_category": "text", "allowed_categories": ["text", "fallback"]},
    },
    "routing_rules": [
        {"name": "code-block", "when": {"prompt_matches": "```|\\bdef \\b"}, "then_category": "code", "priority": 100},
        {"name": "math", "when": {"prompt_matches": "(?i)hesapla"}, "then_category": "reasoning", "priority": 80},
        {"name": "primary", "when": {"always": True}, "then_category": "@department_primary", "priority": 10},
    ],
}


def _orch(states: dict[str, str]) -> Orchestrator:
    orch = Orchestrator.__new__(Orchestrator)
    orch.catalog = CATALOG
    orch.active_model_ids = list(states)
    orch.passive_model_ids = []
    orch.auto_pull = False
    orch.idle_unload_minutes = 10
    orch.max_concurrent_requests = 1
    orch.client = None  # type: ignore
    orch._states = {}
    for mid, status in states.items():
        m = CATALOG["models"][mid]
        s = ModelState(model_id=mid, ollama_tag=m["ollama_tag"], category=m["category"])
        s.status = status
        orch._states[mid] = s
    return orch


def test_code_block_routes_to_code():
    orch = _orch({"txt-1": "ready", "code-1": "ready", "fb": "ready"})
    r = Router(CATALOG, orch)
    decision = r.decide("engineering", "```python\nprint(1)\n```")
    assert decision.category == "code"
    assert decision.model_id == "code-1"


def test_hr_code_block_falls_back_to_primary_text():
    orch = _orch({"txt-1": "ready", "code-1": "ready", "fb": "ready"})
    r = Router(CATALOG, orch)
    decision = r.decide("hr", "```python\nprint(1)\n```")
    assert decision.category == "text"
    assert decision.model_id == "txt-1"


def test_math_keyword_routes_to_reasoning():
    orch = _orch({"txt-1": "ready", "reason-1": "ready", "fb": "ready"})
    r = Router(CATALOG, orch)
    decision = r.decide("finance", "Lutfen 100*1.18 hesapla")
    assert decision.category == "reasoning"


def test_department_primary_when_no_match():
    orch = _orch({"txt-1": "ready", "code-1": "ready", "fb": "ready"})
    r = Router(CATALOG, orch)
    decision = r.decide("hr", "Yillik izin kac gun?")
    assert decision.category == "text"
    assert decision.model_id == "txt-1"


def test_fallback_when_target_not_available():
    orch = _orch({"fb": "ready"})
    r = Router(CATALOG, orch)
    decision = r.decide("engineering", "```js\nconsole.log(1)\n```")
    assert decision.fallback_triggered
    assert decision.model_id == "fb"


def test_category_assignment_overrides_default_selection():
    # Admin 'code' kategorisine txt-1'i atar; katalogda txt-1 aslinda 'text'.
    # Router code'a yonlenince code-1 yerine atanan txt-1'i secmeli.
    orch = _orch({"txt-1": "ready", "code-1": "ready", "fb": "ready"})
    r = Router(CATALOG, orch, category_assignments={"code": ["txt-1"]})
    decision = r.decide("engineering", "```python\nprint(1)\n```")
    assert decision.category == "code"
    assert decision.model_id == "txt-1"


def test_category_assignment_falls_back_when_assigned_not_ready():
    # 'code' yalnizca code-1'e atanmis ama code-1 yok; fallback devreye girer.
    orch = _orch({"fb": "ready"})
    r = Router(CATALOG, orch, category_assignments={"code": ["code-1"]})
    decision = r.decide("engineering", "```python\nprint(1)\n```")
    assert decision.fallback_triggered
    assert decision.model_id == "fb"
