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


# ---------- Sicaklik okuma ----------

class _T:
    def __init__(self, current):
        self.current = current


def test_cpu_temperature_prefers_known_sensor(monkeypatch):
    # acpitz (70.0) global maksimum ama coretemp oncelik listesinde once gelir;
    # oncelik mantigi silinip "global max" yapilirsa bu test 70.0 gorur ve kirilir.
    monkeypatch.setattr(
        sysmonitor.psutil, "sensors_temperatures",
        lambda: {"acpitz": [_T(70.0)], "coretemp": [_T(47.0), _T(52.5)]},
        raising=False,
    )
    assert sysmonitor.cpu_temperature() == 52.5


def test_cpu_temperature_unknown_sensor_still_used(monkeypatch):
    monkeypatch.setattr(
        sysmonitor.psutil, "sensors_temperatures",
        lambda: {"weird_chip": [_T(61.0)]},
        raising=False,
    )
    assert sysmonitor.cpu_temperature() == 61.0


def test_cpu_temperature_filters_garbage_values(monkeypatch):
    monkeypatch.setattr(
        sysmonitor.psutil, "sensors_temperatures",
        lambda: {"coretemp": [_T(0.0), _T(250.0), _T(None)]},
        raising=False,
    )
    monkeypatch.setattr(sysmonitor, "_read_thermal_zones", lambda: None)
    assert sysmonitor.cpu_temperature() is None


def test_disk_temperature_reads_nvme(monkeypatch):
    monkeypatch.setattr(
        sysmonitor.psutil, "sensors_temperatures",
        lambda: {"nvme": [_T(43.0)], "coretemp": [_T(80.0)]},
        raising=False,
    )
    assert sysmonitor.disk_temperature() == 43.0


def test_temperatures_none_when_no_sensors(monkeypatch):
    monkeypatch.setattr(sysmonitor.psutil, "sensors_temperatures", lambda: {}, raising=False)
    monkeypatch.setattr(sysmonitor, "_read_thermal_zones", lambda: None)
    assert sysmonitor.cpu_temperature() is None
    assert sysmonitor.disk_temperature() is None


def test_host_summary_contains_temp_keys():
    h = sysmonitor.host_summary()
    assert "cpu_temp_c" in h
    assert "disk_temp_c" in h


def test_actions_warn_on_high_cpu_temp():
    host = _host()
    host["cpu_temp_c"] = 95.0
    actions = sysmonitor.actions_for_state(host, [])
    assert any("CPU sicakligi" in a["title"] for a in actions)


def test_actions_quiet_on_normal_cpu_temp():
    host = _host()
    host["cpu_temp_c"] = 55.0
    actions = sysmonitor.actions_for_state(host, [])
    assert not any("sicakligi" in a["title"] for a in actions)


def test_cpu_temp_threshold_boundary():
    # Esik tam 90: 89.9 sessiz, 90.0 uyari — esik kaymasi regresyonunu yakalar
    quiet = _host()
    quiet["cpu_temp_c"] = 89.9
    assert not any("CPU sicakligi" in a["title"]
                   for a in sysmonitor.actions_for_state(quiet, []))
    hot = _host()
    hot["cpu_temp_c"] = 90.0
    assert any("CPU sicakligi" in a["title"]
               for a in sysmonitor.actions_for_state(hot, []))


def test_cpu_temperature_fallback_skips_disk_sensors(monkeypatch):
    # CPU sensoru yok, sadece sicak NVMe var: disk degeri CPU sanilmamali
    monkeypatch.setattr(
        sysmonitor.psutil, "sensors_temperatures",
        lambda: {"nvme": [_T(92.0)]},
        raising=False,
    )
    monkeypatch.setattr(sysmonitor, "_read_thermal_zones", lambda: None)
    assert sysmonitor.cpu_temperature() is None


def test_cpu_temperature_uses_thermal_zone_fallback(monkeypatch):
    # Sensor hic yokken /sys/class/thermal fallback'inin BAGLANTISI dogrulanir
    monkeypatch.setattr(sysmonitor.psutil, "sensors_temperatures", lambda: {}, raising=False)
    monkeypatch.setattr(sysmonitor, "_read_thermal_zones", lambda: 47.5)
    assert sysmonitor.cpu_temperature() == 47.5


def test_read_thermal_zones_parses_millidegrees(tmp_path, monkeypatch):
    # Govde testi: milidereceden bolme, 1-120 filtre ve max secimi
    z1 = tmp_path / "thermal_zone0"
    z2 = tmp_path / "thermal_zone1"
    z3 = tmp_path / "thermal_zone2"
    for z in (z1, z2, z3):
        z.mkdir()
    (z1 / "temp").write_text("46500\n")     # 46.5 °C
    (z2 / "temp").write_text("61000\n")     # 61.0 °C  -> max
    (z3 / "temp").write_text("125000\n")    # 125 °C   -> filtre disi
    monkeypatch.setattr(
        sysmonitor.glob, "glob",
        lambda pattern: [str(z / "temp") for z in (z1, z2, z3)],
    )
    assert sysmonitor._read_thermal_zones() == 61.0


def test_read_thermal_zones_handles_garbage(tmp_path, monkeypatch):
    z = tmp_path / "thermal_zone0"
    z.mkdir()
    (z / "temp").write_text("bozuk-deger")
    monkeypatch.setattr(sysmonitor.glob, "glob", lambda pattern: [str(z / "temp")])
    assert sysmonitor._read_thermal_zones() is None
