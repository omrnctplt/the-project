"""AMD sysfs GPU kesfi testleri — sahte /sys/class/drm agaci ile."""

from __future__ import annotations

from app import hwprobe


def _make_card(root, name, vendor, vram_total=None, vram_used=None, product=None):
    device = root / name / "device"
    device.mkdir(parents=True)
    (device / "vendor").write_text(vendor + "\n")
    if vram_total is not None:
        (device / "mem_info_vram_total").write_text(str(vram_total))
    if vram_used is not None:
        (device / "mem_info_vram_used").write_text(str(vram_used))
    if product:
        (device / "product_name").write_text(product + "\n")


def test_amd_sysfs_detects_card(tmp_path):
    _make_card(tmp_path, "card0", "0x1002", vram_total=12 * 1024**3, vram_used=2 * 1024**3, product="Radeon RX 6700 XT")
    gpus = hwprobe._detect_gpus_amd_sysfs(tmp_path)
    assert gpus and len(gpus) == 1
    g = gpus[0]
    assert g["vendor"] == "amd"
    assert g["name"] == "Radeon RX 6700 XT"
    assert g["vram_total_gb"] == 12.0
    assert g["vram_free_gb"] == 10.0
    assert g["source"] == "amdgpu-sysfs"


def test_amd_sysfs_skips_non_amd_and_connectors(tmp_path):
    _make_card(tmp_path, "card0", "0x10de", vram_total=8 * 1024**3)
    (tmp_path / "card0-HDMI-A-1").mkdir()
    _make_card(tmp_path, "card1", "0x1002")
    assert hwprobe._detect_gpus_amd_sysfs(tmp_path) is None


def test_amd_sysfs_missing_root_returns_none(tmp_path):
    assert hwprobe._detect_gpus_amd_sysfs(tmp_path / "yok") is None


def test_detect_gpus_reports_vendor(monkeypatch):
    monkeypatch.setattr(hwprobe, "_detect_gpus_pynvml", lambda: None)
    monkeypatch.setattr(hwprobe, "_detect_gpus_smi", lambda: None)
    monkeypatch.setattr(
        hwprobe, "_detect_gpus_amd_sysfs",
        lambda drm_root=None: [{"index": 0, "name": "X", "vendor": "amd", "vram_total_gb": 8.0, "vram_free_gb": 8.0, "source": "amdgpu-sysfs"}],
    )
    out = hwprobe.detect_gpus()
    assert out["available"] is True
    assert out["vendor"] == "amd"
    assert out["vram_total_gb"] == 8.0


def test_detect_gpus_none(monkeypatch):
    monkeypatch.setattr(hwprobe, "_detect_gpus_pynvml", lambda: None)
    monkeypatch.setattr(hwprobe, "_detect_gpus_smi", lambda: None)
    monkeypatch.setattr(hwprobe, "_detect_gpus_amd_sysfs", lambda drm_root=None: None)
    out = hwprobe.detect_gpus()
    assert out["available"] is False
    assert out["vendor"] is None
