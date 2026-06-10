"""Uzak model kesfi — ollama.com kutuphanesi + HuggingFace GGUF API.

Guncel model listesini internetten ceker ve data/remote_catalog.json'da
TTL'li cache'ler. Ag yoksa stale cache'e, o da yoksa bos listeye duser;
gateway tamamen offline ortamda da sorunsuz calisir (on-premise oncelik).

Kaynaklar:
  - https://ollama.com/library — tek HTML sayfada tum kutuphane. Ollama'nin
    kendi e2e testlerinin dayandigi x-test-* attribute'lari uzerinden parse
    edilir (Tailwind class'larindan cok daha kararli). registry.ollama.ai
    tags/list endpoint'i kaldirildigi icin HTML tek resmi-kaynakli yontemdir.
  - https://huggingface.co/api/models?filter=gguf — resmi JSON API. GGUF
    repolari "ollama pull hf.co/<repo>" ile dogrudan cekilebilir; sharded
    (-00001-of-N) repolar Ollama tarafindan desteklenmedigi icin elenir.

Yeni bir model yayinlandiginda katalog YAML'ina veya UI koduna dokunmak
gerekmez: "Listeyi guncelle" tek basina yeni modelleri gorunur kilar.
"""

from __future__ import annotations

import asyncio
import html as html_mod
import json
import logging
import os
import re
import time
from pathlib import Path
from threading import RLock
from typing import Any

import httpx

from .config import DATA_DIR

log = logging.getLogger(__name__)

OLLAMA_LIBRARY_URL = "https://ollama.com/library"
HF_API_URL = "https://huggingface.co/api/models"
CACHE_PATH = DATA_DIR / "remote_catalog.json"
CACHE_TTL_HOURS = float(os.getenv("DISCOVERY_TTL_HOURS", "24"))
HF_LIMIT = int(os.getenv("DISCOVERY_HF_LIMIT", "40"))
FETCH_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
USER_AGENT = "Mozilla/5.0 (compatible; InferenceHub/0.6; +https://github.com/omrnctplt/the-project)"

# Yapinin degistigini anlamak icin alt sinir: ollama.com/library 200+ model
# barindirir; bundan az parse edebiliyorsak selector'lar kirilmis demektir.
MIN_EXPECTED_OLLAMA_MODELS = 50

_lock = RLock()

_RE_ENTRY = re.compile(r"<li[^>]*x-test-model[^>]*>(.*?)</li>", re.S)
_RE_NAME = re.compile(r'x-test-model-title[^>]*title="([^"]+)"')
_RE_DESC = re.compile(r'<p class="max-w-lg break-words[^"]*">(.*?)</p>', re.S)
_RE_PULLS = re.compile(r"<span[^>]*x-test-pull-count[^>]*>([^<]+)</span>")
_RE_SIZES = re.compile(r"<span[^>]*x-test-size[^>]*>([^<]+)</span>")
_RE_CAPS = re.compile(r"<span[^>]*x-test-capability[^>]*>([^<]+)</span>")
_RE_UPDATED = re.compile(r"<span[^>]*x-test-updated[^>]*>([^<]+)</span>")
_RE_PARAMS_IN_NAME = re.compile(r"(\d+(?:[._]\d+)?)\s*[bB](?:\b|[-_])")


def parse_pull_count(text: str) -> int:
    t = (text or "").strip().upper().replace(",", ".")
    m = re.match(r"^([\d.]+)\s*([KMB]?)$", t)
    if not m:
        return 0
    value = float(m.group(1))
    mult = {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[m.group(2)]
    return int(value * mult)


def parse_size_label(label: str) -> float | None:
    """'7b' -> 7.0, '0.6b' -> 0.6, '8x7b' -> 56.0, '360m' -> 0.36, 'e2b' -> 2.0."""
    t = (label or "").strip().lower().lstrip("e")
    m = re.match(r"^(?:(\d+)x)?(\d+(?:\.\d+)?)([bm])$", t)
    if not m:
        return None
    mult = int(m.group(1) or 1)
    value = float(m.group(2)) * mult
    if m.group(3) == "m":
        value /= 1000.0
    return round(value, 3)


def estimate_ram_gb(parameters_b: float) -> float:
    """Q4_K_M kuantizasyon + calisma sirasi ek yuk icin yaklasik RAM (GB).

    Katsayilar mevcut katalogdaki elle dogrulanmis degerlere kalibre edildi
    (orn. 8B -> 5.5 GB, 14B -> 10 GB, 70B -> 43 GB).
    """
    p = max(0.0, float(parameters_b))
    if p <= 0:
        return 0.0
    if p < 2:
        factor = 0.9
    elif p < 8:
        factor = 0.75
    elif p < 20:
        factor = 0.7
    elif p < 80:
        factor = 0.65
    else:
        factor = 0.6
    return round(max(0.4, p * factor), 1)


def tier_for_ram(ram_gb: float) -> str:
    if ram_gb <= 4:
        return "edge"
    if ram_gb <= 16:
        return "laptop"
    if ram_gb <= 48:
        return "workstation"
    return "datacenter"


def guess_category(name: str, description: str = "", capabilities: list[str] | None = None) -> str | None:
    """Model adi/aciklamasi/yeteneklerinden kategori tahmini. None => listeleme (embedding)."""
    caps = [c.lower() for c in (capabilities or [])]
    hay = f"{name} {description}".lower()
    if "embedding" in caps or "embed" in name.lower():
        return None
    if re.search(r"coder|codestral|codellama|codegemma|starcoder|\bcode\b|sql", hay):
        return "code"
    if "thinking" in caps or re.search(r"\br1\b|qwq|reason|think|math|phi-?4|o1\b", hay):
        return "reasoning"
    if re.search(r"dolphin|hermes|roleplay|uncensored|persona|character", hay):
        return "persona"
    return "text"


def parse_ollama_library(page_html: str) -> list[dict[str, Any]]:
    """ollama.com/library HTML'inden ham model girisleri cikarir."""
    entries: list[dict[str, Any]] = []
    for chunk in _RE_ENTRY.findall(page_html or ""):
        name_m = _RE_NAME.search(chunk)
        if not name_m:
            continue
        name = name_m.group(1).strip()
        desc_m = _RE_DESC.search(chunk)
        description = ""
        if desc_m:
            description = html_mod.unescape(re.sub(r"<[^>]+>", "", desc_m.group(1))).strip()
        pulls_m = _RE_PULLS.search(chunk)
        updated_m = _RE_UPDATED.search(chunk)
        entries.append({
            "name": name,
            "description": description,
            "pulls": parse_pull_count(pulls_m.group(1)) if pulls_m else 0,
            "sizes": [s.strip() for s in _RE_SIZES.findall(chunk)],
            "capabilities": [c.strip() for c in _RE_CAPS.findall(chunk)],
            "updated": updated_m.group(1).strip() if updated_m else None,
        })
    return entries


def ollama_entries_to_models(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ham girisleri (model x boyut) normalize edilmis item listesine acar.

    Boyut etiketi olmayan girisler ollama.com'un CLOUD modelleridir
    (deepseek-v4, kimi-k2.6, glm-5.1 vb.) — lokal pull edilemezler ama
    guncel gelismelerin gorunurlugu icin listede `cloud: true` ile yer alir.
    """
    items: list[dict[str, Any]] = []
    for e in entries:
        category = guess_category(e["name"], e.get("description", ""), e.get("capabilities"))
        if category is None:
            continue
        sizes = e.get("sizes") or []
        if not sizes:
            items.append({
                "key": f"ollama:{e['name']}:cloud",
                "provider": "ollama",
                "name": e["name"],
                "tag": e["name"],
                "label": e["name"].replace("-", " ").title(),
                "blurb": e.get("description", ""),
                "category": category,
                "parameters_b": None,
                "approx_gb": None,
                "tier": None,
                "cloud": True,
                "popularity": e.get("pulls", 0),
                "updated": e.get("updated"),
                "capabilities": e.get("capabilities") or [],
            })
            continue
        for size_label in sizes:
            params = parse_size_label(size_label)
            if params is None:
                continue
            ram = estimate_ram_gb(params)
            items.append({
                "key": f"ollama:{e['name']}:{size_label}",
                "provider": "ollama",
                "name": e["name"],
                "tag": f"{e['name']}:{size_label}",
                "label": f"{e['name'].replace('-', ' ').title()} {size_label.upper()}",
                "blurb": e.get("description", ""),
                "category": category,
                "parameters_b": params,
                "approx_gb": ram,
                "tier": tier_for_ram(ram),
                "cloud": False,
                "popularity": e.get("pulls", 0),
                "updated": e.get("updated"),
                "capabilities": e.get("capabilities") or [],
            })
    return items


def parse_hf_models(payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """HuggingFace /api/models yanitini normalize eder.

    Sharded GGUF (-00001-of-N) repolar elenir: Ollama desteklemiyor
    (ollama/ollama#8326). Parametre sayisi repo adindan cikarilamayan
    repolar da elenir (RAM tahmini yapilamaz).
    """
    items: list[dict[str, Any]] = []
    for m in payload or []:
        repo_id = str(m.get("id") or m.get("modelId") or "")
        if not repo_id or m.get("private") or m.get("gated"):
            continue
        siblings = m.get("siblings") or []
        ggufs = [s.get("rfilename", "") for s in siblings if str(s.get("rfilename", "")).endswith(".gguf")]
        if ggufs and all("-of-" in g for g in ggufs):
            continue
        params_m = _RE_PARAMS_IN_NAME.search(repo_id.split("/")[-1])
        if not params_m:
            continue
        params = float(params_m.group(1).replace("_", "."))
        ram = estimate_ram_gb(params)
        category = guess_category(repo_id, "", m.get("tags"))
        if category is None:
            continue
        downloads = int(m.get("downloads") or 0)
        items.append({
            "key": f"hf:{repo_id}",
            "provider": "huggingface",
            "name": repo_id,
            "tag": f"hf.co/{repo_id}",
            "label": repo_id.split("/")[-1].replace("-GGUF", "").replace("-gguf", ""),
            "blurb": f"HuggingFace GGUF — {repo_id.split('/')[0]} ({downloads:,} indirme)".replace(",", "."),
            "category": category,
            "parameters_b": params,
            "approx_gb": ram,
            "tier": tier_for_ram(ram),
            "cloud": False,
            "popularity": downloads,
            "updated": m.get("lastModified") or m.get("createdAt"),
            "capabilities": [],
        })
    return items


async def fetch_ollama_library(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    r = await client.get(OLLAMA_LIBRARY_URL, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
    r.raise_for_status()
    entries = parse_ollama_library(r.text)
    if len(entries) < MIN_EXPECTED_OLLAMA_MODELS:
        raise ValueError(
            f"ollama.com/library beklenenden az model dondurdu ({len(entries)}); "
            "sayfa yapisi degismis olabilir"
        )
    return ollama_entries_to_models(entries)


async def fetch_huggingface(client: httpx.AsyncClient, limit: int = HF_LIMIT) -> list[dict[str, Any]]:
    r = await client.get(
        HF_API_URL,
        params={
            "filter": "gguf",
            "pipeline_tag": "text-generation",
            "sort": "downloads",
            "direction": "-1",
            "limit": str(limit),
            "full": "true",
        },
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    )
    r.raise_for_status()
    return parse_hf_models(r.json())


def load_cache() -> dict[str, Any] | None:
    with _lock:
        if not CACHE_PATH.exists():
            return None
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None


def save_cache(data: dict[str, Any]) -> None:
    with _lock:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(CACHE_PATH)


def cache_is_fresh(cache: dict[str, Any] | None, ttl_hours: float = CACHE_TTL_HOURS) -> bool:
    if not cache:
        return False
    fetched_at = float(cache.get("fetched_at") or 0)
    return (time.time() - fetched_at) < ttl_hours * 3600


async def get_remote_catalog(
    force: bool = False,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Birlesik uzak katalog: once taze cache, sonra ag, en son stale cache."""
    cache = load_cache()
    if not force and cache_is_fresh(cache):
        return cache  # type: ignore[return-value]

    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=FETCH_TIMEOUT)
    errors: list[str] = []
    models: list[dict[str, Any]] = []
    try:
        results = await asyncio.gather(
            fetch_ollama_library(client),
            fetch_huggingface(client),
            return_exceptions=True,
        )
        for source, result in zip(("ollama.com", "huggingface.co"), results):
            if isinstance(result, BaseException):
                errors.append(f"{source}: {result}")
                log.warning("Uzak kesif kaynagi basarisiz [%s]: %s", source, result)
            else:
                models.extend(result)
    finally:
        if owns_client:
            await client.aclose()

    if not models:
        if cache:
            log.warning("Uzak kesif tamamen basarisiz; eski cache kullaniliyor (%s)", errors)
            cache["stale"] = True
            cache["errors"] = errors
            return cache
        return {"fetched_at": 0, "models": [], "errors": errors, "stale": False}

    seen: set[str] = set()
    deduped = []
    for it in models:
        if it["key"] in seen:
            continue
        seen.add(it["key"])
        deduped.append(it)

    data = {
        "fetched_at": time.time(),
        "models": deduped,
        "errors": errors,
        "stale": False,
        "sources": {
            "ollama": sum(1 for m in deduped if m["provider"] == "ollama"),
            "huggingface": sum(1 for m in deduped if m["provider"] == "huggingface"),
        },
    }
    try:
        save_cache(data)
    except OSError as exc:
        log.warning("Uzak katalog cache yazilamadi: %s", exc)
    return data
