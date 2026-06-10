"""Sistem kaynak monitoru — GPU metrikleri ve aksiyon onerileri."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import sysmonitor


def test_gpu_stats_returns_list_without_gpu():
    # GPU'suz ortamda (CI dahil) sessizce bos liste donmeli, exception degil
    result = sysmonitor.gpu_stats()
    assert isinstance(result, list)


def test_snapshot_contains_gpus_key():
    snap = sysmonitor.snapshot()
    assert "gpus" in snap
    assert isinstance(snap["gpus"], list)
    assert "host" in snap and "actions" in snap


def _host(mem=50.0, cpu=50.0, disk=50.0):
    return {"memory_percent": mem, "cpu_percent": cpu, "disk_percent": disk}


def test_actions_warn_on_high_vram():
    gpus = [{"index": 0, "name": "RTX 4090", "vram_percent": 95.0, "temperature_c": 60}]
    actions = sysmonitor.actions_for_state(_host(), [], gpus)
    assert any("VRAM" in a["title"] for a in actions)


def test_actions_warn_on_high_gpu_temp():
    gpus = [{"index": 0, "name": "RTX 4090", "vram_percent": 40.0, "temperature_c": 90}]
    actions = sysmonitor.actions_for_state(_host(), [], gpus)
    assert any("sicaklik" in a["title"] for a in actions)


def test_actions_quiet_on_healthy_gpu():
    gpus = [{"index": 0, "name": "RTX 4090", "vram_percent": 40.0, "temperature_c": 60}]
    actions = sysmonitor.actions_for_state(_host(), [], gpus)
    assert not any("GPU" in a["title"] for a in actions)


def test_actions_backward_compatible_without_gpus():
    actions = sysmonitor.actions_for_state(_host(disk=95.0), [])
    assert any("Disk" in a["title"] for a in actions)
