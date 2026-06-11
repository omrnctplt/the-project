"""Yuk simulatoru — N sanal kullanici, M saniye, departman karisimi."""

from __future__ import annotations

import asyncio
import os
import random
import statistics
import time
from dataclasses import dataclass, field

import httpx

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://gateway:7070")
SIM_USERS = int(os.getenv("SIM_USERS", "10"))
SIM_DURATION_SEC = int(os.getenv("SIM_DURATION_SEC", "120"))
SIM_THINK = float(os.getenv("SIM_THINK_TIME_SEC", "2.0"))
SIM_MIX = os.getenv("SIM_DEPT_MIX", "hr:0.3,engineering:0.5,general:0.2")

USERS_BY_DEPT = {
    "hr": [("hr_user", "hr123")],
    "engineering": [("dev_user", "dev123")],
    "legal": [("legal_user", "legal123")],
    "finance": [("finance_user", "fin123")],
    "marketing": [("marketing_user", "mkt123")],
    "general": [("guest", "guest")],
}

PROMPTS = {
    "hr": [
        "Yillik izin politikasini ozetler misin?",
        "Yeni calisan icin 5 maddelik oryantasyon plani yaz.",
        "Performans degerlendirme gorusmesi icin 5 acik uclu soru oner.",
        "Uzaktan calisma politikasini ozetle.",
        "Bir maas zammi talep mektubu nasil yazilir?",
    ],
    "engineering": [
        "```python\ndef fib(n):\n    return fib(n-1) + fib(n-2)\n```\nBu kodun problemi ne, nasil duzeltirsin?",
        "FastAPI'de async endpoint nasil yazilir? Kisa ornek ver.",
        "SQL injection nedir, parametreli sorgu ile nasil onlenir?",
        "Bir REST API endpoint'i icin pytest unit test yaz.",
        "function debounce(fn, ms) { /* ... */ } -> bu JS fonksiyonunu tamamla.",
    ],
    "legal": [
        "KVKK kapsaminda veri sahibi haklarini sayar misin?",
        "Bir gizlilik sozlesmesinin temel maddeleri nelerdir?",
        "Calisan ile yapilan rekabet yasagi sozlesmesi genelde neler iceriyor?",
    ],
    "finance": [
        "100.000 TL'nin %18 KDV dahil tutarini hesapla.",
        "Aylik 5000 TL gelir, 3000 TL gideri olan birinin yillik net tasarrufu nedir? Hesapla.",
        "Basit faiz formulu nedir, %12 ile 24 ayda 10.000 TL ne kadar getirir? Hesapla.",
    ],
    "marketing": [
        "Yeni cikan bir mobil uygulama icin 3 farkli slogan oner.",
        "Hedef kitlesi 20-30 yas arasi bir kahve markasi icin sosyal medya kampanyasi fikirleri ver.",
        "Bir blog yazisi icin SEO uyumlu 5 baslik onerisi yaz.",
    ],
    "general": [
        "Turkiye'nin en kalabalik 5 sehrini liste halinde yaz.",
        "Yapay zekanin gunluk yasamdaki kullanim alanlarini ozetle.",
        "Saglikli beslenme icin 3 oneride bulun.",
    ],
}


@dataclass
class Stats:
    requests_ok: int = 0
    requests_err: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    by_department: dict[str, int] = field(default_factory=dict)
    by_model: dict[str, int] = field(default_factory=dict)
    fallbacks: int = 0


def parse_mix(mix: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for part in mix.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            k, v = part.split(":")
            out[k.strip()] = float(v)
        except ValueError:
            continue
    total = sum(out.values()) or 1.0
    return {k: v / total for k, v in out.items()}


def assign_departments(n: int, mix: dict[str, float]) -> list[str]:
    assignments: list[str] = []
    for dept, ratio in mix.items():
        count = max(1, int(round(n * ratio)))
        assignments.extend([dept] * count)
    while len(assignments) < n:
        assignments.append(next(iter(mix)))
    return assignments[:n]


async def login(client: httpx.AsyncClient, username: str, password: str) -> str:
    r = await client.post("/login", json={"username": username, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


async def virtual_user(idx: int, department: str, deadline: float, stats: Stats) -> None:
    users = USERS_BY_DEPT.get(department) or USERS_BY_DEPT["general"]
    username, password = random.choice(users)
    prompts = PROMPTS.get(department) or PROMPTS["general"]

    async with httpx.AsyncClient(base_url=GATEWAY_URL, timeout=httpx.Timeout(60.0)) as client:
        for _attempt in range(5):
            try:
                token = await login(client, username, password)
                break
            except Exception as exc:
                print(f"[{idx}] Login basarisiz ({exc}), tekrar denenecek...")
                await asyncio.sleep(2)
        else:
            print(f"[{idx}] Login tamamen basarisiz, sanal kullanici cikiyor.")
            return

        client.headers["Authorization"] = f"Bearer {token}"
        while time.time() < deadline:
            prompt = random.choice(prompts)
            t0 = time.perf_counter()
            try:
                r = await client.post("/api/v1/chat", json={"prompt": prompt})
                dt = (time.perf_counter() - t0) * 1000
                if r.status_code == 200:
                    data = r.json()
                    stats.requests_ok += 1
                    stats.latencies_ms.append(dt)
                    stats.by_department[department] = stats.by_department.get(department, 0) + 1
                    mid = str(data.get("model_id", "?"))
                    stats.by_model[mid] = stats.by_model.get(mid, 0) + 1
                    if data.get("fallback_triggered"):
                        stats.fallbacks += 1
                elif r.status_code == 429:
                    stats.requests_err += 1
                    await asyncio.sleep(1.5)
                else:
                    stats.requests_err += 1
            except Exception as exc:
                stats.requests_err += 1
                print(f"[{idx}] istek hatasi: {exc}")
            jitter = random.uniform(0.5, 1.5)
            await asyncio.sleep(SIM_THINK * jitter)


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = int(round((p / 100.0) * (len(s) - 1)))
    return s[k]


def print_report(stats: Stats, duration: float) -> None:
    total = stats.requests_ok + stats.requests_err
    print("\n" + "=" * 60)
    print("SIMULASYON RAPORU")
    print("=" * 60)
    print(f"Sure                : {duration:.1f}s")
    print(f"Toplam istek        : {total}")
    print(f"  Basarili          : {stats.requests_ok}")
    print(f"  Hatali            : {stats.requests_err}")
    print(f"Throughput          : {total/duration:.2f} req/s")
    print(f"Fallback tetiklendi : {stats.fallbacks}")
    if stats.latencies_ms:
        print(f"Latency min/avg/max : "
              f"{min(stats.latencies_ms):.0f} / "
              f"{statistics.mean(stats.latencies_ms):.0f} / "
              f"{max(stats.latencies_ms):.0f} ms")
        print(f"Latency p50/p95/p99 : "
              f"{percentile(stats.latencies_ms, 50):.0f} / "
              f"{percentile(stats.latencies_ms, 95):.0f} / "
              f"{percentile(stats.latencies_ms, 99):.0f} ms")
    if stats.by_department:
        print("\nDepartman bazinda:")
        for d, c in sorted(stats.by_department.items(), key=lambda kv: -kv[1]):
            print(f"  {d:14s} {c}")
    if stats.by_model:
        print("\nModel bazinda:")
        for m, c in sorted(stats.by_model.items(), key=lambda kv: -kv[1]):
            print(f"  {m:30s} {c}")
    print("=" * 60)


async def wait_for_gateway(timeout: int = 120) -> None:
    deadline = time.time() + timeout
    async with httpx.AsyncClient(base_url=GATEWAY_URL, timeout=httpx.Timeout(5.0)) as client:
        while time.time() < deadline:
            try:
                r = await client.get("/readyz")
                if r.status_code == 200 and r.json().get("ready"):
                    print("Gateway hazir.")
                    return
            except httpx.HTTPError:
                pass
            print("Gateway bekleniyor...")
            await asyncio.sleep(3)
    print("Gateway hazir hale gelmedi; yine de devam ediliyor.")


async def main() -> None:
    print(f"Hedef: {GATEWAY_URL}")
    print(f"Kullanici: {SIM_USERS}, sure: {SIM_DURATION_SEC}s, karisim: {SIM_MIX}")
    await wait_for_gateway()

    mix = parse_mix(SIM_MIX)
    assignments = assign_departments(SIM_USERS, mix)
    stats = Stats()
    deadline = time.time() + SIM_DURATION_SEC
    start = time.time()

    tasks = [
        asyncio.create_task(virtual_user(i, dept, deadline, stats))
        for i, dept in enumerate(assignments)
    ]
    await asyncio.gather(*tasks, return_exceptions=True)
    print_report(stats, time.time() - start)


if __name__ == "__main__":
    asyncio.run(main())
