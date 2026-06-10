# Inference Hub

[![tests](https://github.com/omrnctplt/the-project/actions/workflows/test.yml/badge.svg)](https://github.com/omrnctplt/the-project/actions/workflows/test.yml)
[![python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![fastapi](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com/)
[![docker](https://img.shields.io/badge/docker-compose-2496ED.svg)](https://docs.docker.com/compose/)
[![license](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> **Departman bazli, donanima gore kendini ayarlayan, sifir konfigurasyonla tek `docker compose up -d --build` ile ayaga kalkan, on-premise LLM gateway.**

Kucuk ekipler icin Ollama'nin onunde duran bir yonlendirme katmani. Sistem ilk acilista donanimi olcer, uygun **kapasite profilini** secer, **departman + prompt** tabanli akilli yonlendirme yapar, butun istekleri **denetler**. **Canli model kesfi** ollama.com + HuggingFace'ten guncel model listesini otomatik ceker — yeni bir model ciktiginda arayuzu veya katalogu elle guncellemek gerekmez. UI, REST API, Prometheus metrikleri ve Grafana paneli kutudan cikar cikmaz hazirdir.

---

## Yetenekler

### Calistirma
- **Tek komut, sifir konfigurasyon:** `docker compose up -d --build` — `.env` dosyasi bile gerekmez; `JWT_SECRET` verilmezse sistem guvenli bir secret uretip `data/jwt_secret` dosyasinda kalici saklar
- **Port preflight:** `make up` ile cakisan portlari otomatik tespit, oneri ile uyari
- **Resource limit'leri:** gateway ve ollama icin compose `mem_limit` + `cpus`
- **Lazy pull:** Kullanici secinceye kadar disk veya ag yuku yok — model otomatik inmez
- **Bootstrap stage stream:** Donanim tarama, plan, orchestrator baslama her adim canli UI'da

### UI (premium, sidebar layout)
- **Onboarding sihirbazi:** Ilk acilista donanim ozeti + kategoriye gore filtrelenmis model kartlari (yesil cerceveli olanlar butceye sigar)
- **ChatGPT-tarzi sohbet:** **Cok turlu baglam** (onceki turlar modele gider), sol konusma gecmisi (kullanici-bazli, cikista silinir), akan mesajlar, **markdown render** (kod blogu kopyala butonlu), **Durdur / yeniden uret / tok/s**, markdown disa aktar, departman bazli ornek prompt kartlari
- **Modeller sayfasi:** Arama + kategori/durum filtresi + accordion + model kartlari (pull / sil / hizli test)
- **Sistem kaynaklari sayfasi (admin):** Host CPU/mem/disk progress bar, top processes, Docker container stats, otomatik aksiyon onerileri
- **Yonetim:** Profil/kullanicilar/kullanim/denetim tab'lari + sifre degistirme modal
- **Genel bakis:** Donanim, kapasite, model durumu + **bagimliliksiz SVG grafikler** (bellek butcesi donut'u, model durumu barlari)
- **Tema:** Acik / koyu / sistem temasi — kalici tercih, FOUC'suz on-yukleme
- **Mobil + erisilebilirlik:** Hamburger drawer, dokunmatik uyum, dusuk-guc cihazda efekt kismasi, gorunur odak halkalari, `prefers-reduced-motion`

### Routing & kapasite
- **4 profil:** `lite` (cok dusuk kaynak) / `balanced` (laptop) / `performance` (GPU) / `auto`
- **Departman bazli kaynak sinifi:** `light` / `medium` / `heavy` + `preferred_size`
- **Prompt-aware:** Kisa prompt kucuk modele, uzun prompt buyuk modele yonlendirilir
- **Keyword + always rule:** Kod blogu icin `code`, matematik icin `reasoning`, aksi halde departman primary
- **Fallback chain:** Hedef kategoride hazir model yoksa fallback'a duser

### Model katalogu & canli kesif
- **Canli kesif:** ollama.com kutuphanesi (~230 model, tum boyut varyantlari) + HuggingFace GGUF API'sinden guncel model listesi otomatik cekilir, 24 saat TTL ile cache'lenir — **yeni model ciktiginda UI/katalog guncellemesi gerekmez**, "Listeyi guncelle" yeterli
- **Cloud modeller de gorunur:** DeepSeek-V4, Kimi-K2.6, GLM-5.1 gibi yalnizca Ollama Cloud'da calisan modeller listede "☁ cloud" rozetiyle yer alir; on-premise kurulamayacaklari (veri disari cikar) acikca belirtilir
- **Offline dostu:** Ag yoksa eski kopyaya, o da yoksa statik kataloga duser; on-premise ortam hic bozulmaz
- **59 modellik statik havuz** — donanim tier'li (edge/laptop/workstation/datacenter): **Gemma 4, Qwen3.5/3.6, Granite 4.1, Nemotron 3, Mistral Medium 3.5, LFM2.5**, Llama 4, DeepSeek-V3/R1, Phi-4, gpt-oss...
- **Donanima gore dinamik oneri** — hem statik hem canli kesif, donanim tier'ina gore uygun modelleri one cikarir (laptop'ta kucuk, H100/H200'de dev modeller); RAM ihtiyaci parametre sayisindan otomatik tahmin edilir
- **Tek tikla kur/kaldir:** kesif kartindan "+ Kur" katalog kaydi + indirmeyi tek adimda baslatir; "Ollama'dan sil" diski tek tikla bosaltir
- **Persona / rol yapma** kategorisi + admin **kategori → model atamasi** (Ayarlar sayfasi)
- **HuggingFace destegi** — `hf.co/...` GGUF tag'leri ile ekleme + pull; sharded (Ollama'nin desteklemedigi) repolar otomatik elenir
- **Inspect:** Ollama `/api/show` ile gercek boyut tahmini
- **Dry-run:** Modeli eklemeden once "tum profillerde butceye sigar mi?" raporu
- **Override katmani:** `data/catalog_overrides.yaml` ile kullanici eklemeleri YAML'a dokunmadan saklanir

### Gozlemlenebilirlik (Observability)
- **Prometheus metrikleri:** `/metrics` — istek/latency/token/inflight/fallback/rate-limit
- **Grafana dashboard'u:** Hazir provisioned, AI Gateway klasoru altinda alert kurallari
- **Prometheus alert rule'lari:** GatewayDown, HighErrorRate, HighFallbackRate, HighLatencyP95, NoActiveModel, ModelPullStuck, HighRateLimit
- **Audit log:** SQLite, prompt **hash**'i ile saklanir (KVKK uyumlu — ham prompt tutulmaz)
- **Usage tracking:** Kullanici × gun × model bazli token/istek/latency

### Guvenlik & KVKK
Ayrintili veri envanteri ve uyum onlemleri icin: **[SECURITY.md](SECURITY.md)**
- **KVKK uyumu:** aydinlatma metni (`/ui/privacy`), veri minimizasyonu (prompt'un yalnizca salt'li SHA-256 ozeti saklanir, IP toplanmaz), `RETENTION_DAYS` ile otomatik veri imha, silme hakki endpoint'leri (`DELETE /api/v1/users/{u}/data` ve `/api/v1/users/{u}`)
- **JWT auth** (`HS256`, 8 saatlik TTL) — secret verilmezse otomatik uretilir ve kalici saklanir
- **bcrypt** ile sifre hashleme; yeni parolalar en az 8 karakter
- **Login brute-force korumasi** — kullanici basina dakikada 10 deneme
- **Rate limit** departman bazli (in-memory sliding window); 429 yanitlarinda `Retry-After`
- **Rol bazli erisim:** `admin` / `user` — UI da rol farkindadir (yetkisiz butonlar gizlenir)
- **DEMO_MODE=false** ile uretim modu: yalnizca admin seed edilir, demo parola listesi gizlenir
- **Ollama portu 127.0.0.1'e kilitli** — gateway'in auth/audit katmani agdan atlanamaz
- **HTTP guvenlik basliklari:** CSP, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`

---

## Hizli Baslangic

### Gereksinimler
- Docker Engine veya Docker Desktop
- En az **6 GB RAM**, **20 GB disk**
- GPU opsiyonel (NVIDIA Container Toolkit varsa kullanilir)

### 1. Tek komut

```bash
docker compose up -d --build
```

Hepsi bu. `.env` dosyasi gerekmez: `JWT_SECRET` otomatik uretilir, portlar ve
limitler mantikli varsayilanlarla gelir, sistem ilk acilista donanimi olcup
kendine uygun kapasite profilini secer.

GPU overlay ile (NVIDIA Container Toolkit gerekir):
```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

### 2. Alternatif: `make up` (preflight'li)

```bash
make up
```

`make up` su adimlari yapar:
1. **Preflight** (`scripts/preflight.sh` veya `.ps1`): port cakismasi, Docker daemon, disk, RAM kontrolu
2. `.env` yoksa otomatik olusturur (`.env.example`'dan)
3. Compose build + up (gateway, ollama, prometheus, grafana)
4. Servis URL'lerini yazdirir

### 3. UI'yi ac

| URL | Aciklama |
|---|---|
| **http://localhost:8080** | Inference Hub — login → genel bakis |
| http://localhost:8080/docs | OpenAPI / Swagger |
| http://localhost:3000 | Grafana (`admin/admin`) |
| http://localhost:9090 | Prometheus (`/alerts` ile alarm durumu) |
| http://localhost:11434 | Dogrudan Ollama API |

---

## Demo hesaplari

| Kullanici | Sifre | Departman | Rol | resource_class | preferred_size |
|---|---|---|---|---|---|
| `admin` | `admin` | engineering | **admin** | heavy | large |
| `dev_user` | `dev123` | engineering | user | heavy | large |
| `hr_user` | `hr123` | hr | user | light | small |
| `finance_user` | `fin123` | finance | user | medium | medium |
| `legal_user` | `legal123` | legal | user | medium | medium |
| `marketing_user` | `mkt123` | marketing | user | light | small |
| `guest` | `guest` | general | user | light | small |

> Giris ekranindaki demo tablosuna **tiklayarak** formu otomatik doldurabilirsiniz.
> `DEMO_MODE=true` iken bu parolalar her acilista tabloya esitlenir — listelenen
> her hesap her zaman calisir. Uretimde `DEMO_MODE=false` yapin (yalnizca admin
> olusur, demo listesi gizlenir); `ADMIN_PASSWORD` env var'i admin parolasini belirler.

---

## Mimari

```
                     +----------------------+
                     |   Tarayici / curl    |
                     +----------+-----------+
                                | JWT (Bearer)
                                v
+------------------------------------------------------------+
|                  FastAPI Gateway :8080                     |
|                                                            |
|  Auth          : JWT + bcrypt + SQLite (users.db)          |
|  Router        : departman + regex + prompt-size           |
|  Capacity      : profil bazli plan (lite/balanced/perf)    |
|  Orchestrator  : lazy pull, semaphore, idle unload         |
|  Sysmonitor    : psutil host stats + docker stats          |
|  Audit         : SQLite + indexlenmis (audit.db)           |
|  Usage         : SQLite (usage.db) + in-mem rate limit     |
|  Metrics       : Prometheus client (/metrics)              |
+----+------------------+------------------+-----------------+
     |                  |                  |
     v                  v                  v
+----------+      +-----------+      +-----------+
|  Ollama  |      |Prometheus |      |  Grafana  |
|  :11434  |      |  :9090    |      |  :3000    |
+----------+      +-----------+      +-----------+
     |
     v
 (model storage / VRAM-RAM)
```

---

## Kapasite Profilleri

Donanima gore otomatik secilir; `.env`'de `CAPACITY_PROFILE` ile manuel override edilebilir.

| Profil | RAM/VRAM butce orani | Max aktif | Max yuklu | Paralel | Kategoriler |
|---|---|---|---|---|---|
| `lite`        | %25 CPU / %55 GPU | 1 | 1 | 1 | fallback |
| `balanced`    | %40 CPU / %70 GPU | 3 | 1 | 1 | fallback, text, code |
| `performance` | %55 CPU / %80 GPU | 6 | 2 | 2 | fallback, text, code, reasoning |

**Otomatik secim:**
- VRAM ≥ 12 GB veya RAM ≥ 16 GB → `performance` (GPU varsa)
- 6-16 GB → `balanced`
- < 6 GB → `lite`

---

## Yonlendirme (Routing) kurallari

`config/model_catalog.yaml` icindeki `routing_rules` bolumunden duzenlenebilir.

```yaml
routing_rules:
  - name: "Kod blogu varsa code"
    when:
      prompt_matches: "```|\\bdef \\b|\\bfunction \\b|\\bclass \\b|\\bSELECT \\b|=>"
    then_category: code
    priority: 100

  - name: "Matematik anahtar kelimesi varsa reasoning"
    when:
      prompt_matches: "(?i)hesapla|formul|matematik|integral|denklem|=\\s*\\?"
    then_category: reasoning
    priority: 80

  - name: "Departman primary kategorisi"
    when:
      always: true
    then_category: "@department_primary"
    priority: 10
```

**Prompt-aware boyut secimi:** Kural eslesince, departmanin `preferred_size`'i (small/medium/large) baz alinir; prompt > 2000 char ise bir boyut buyuk, kisa + light dept ise bir boyut kucuk modele yonlendirilir. Kategoride hazir model yoksa **fallback**'a duser.

---

## Model katalogu

`config/model_catalog.yaml` icinde 59 model tanimli (her birinde donanim `tier`'i + `source` + `license`). Aktif/pasif ayrimi profil + donanima gore otomatik; discover, donanim tier'ina gore oneri yapar (edge → laptop → workstation → datacenter).

### Yeni model ekleme (uc yontem)

**a) UI uzerinden (admin):** Modeller sayfasi → **+ Yeni model ekle** → Tag yaz → **Boyutu tahmin et** → **Butceye sigar mi?** → Ekle.

**b) API uzerinden:**
```bash
TOKEN=$(curl -s -X POST http://localhost:8080/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' | jq -r .access_token)

curl -X POST http://localhost:8080/api/v1/system/catalog/models \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model_id":"qwen3-4b","ollama_tag":"qwen3:4b","category":"text","ram_gb":3.0}'
```

**c) YAML uzerinden:** `config/model_catalog.yaml`'a satir eklenir, container restart edilir.

### Onerilen modeller (Haziran 2026)

| Tag | Kategori | ~Boyut | Notlar |
|---|---|---|---|
| `gemma4:e2b` ... `gemma4:31b` | text | 1.5 - 20 GB | **En yeni**: gorsel + ses + thinking, her boyutta frontier |
| `qwen3.5:0.8b` ... `qwen3.5:122b` | text/fallback | 0.7 - 73 GB | Yeni nesil multimodal + thinking |
| `qwen3.6:27b` / `qwen3.6:35b` | code/reasoning | 17.6 / 22.8 GB | Agentic coding'de sicrama |
| `granite4.1:8b` / `:30b` | text | 5.6 / 19.5 GB | IBM kurumsal — RAG + JSON cikti |
| `deepseek-r1:1.5b` / `7b` / `14b` | reasoning | 1.5 - 9 GB | Chain-of-thought distill |
| `qwen2.5-coder:1.5b/3b/7b/14b` | code | 1.2 - 9 GB | Kod tamamlama / refactor |
| `lfm2.5:8b` | text | 5.6 GB | Tuketici donaniminda hizli tool calling |
| `nemotron-cascade-2:30b` | reasoning | 19.5 GB | MoE (3B aktif) — verimli agentic |
| `mistral-medium-3.5:128b` | text | 77 GB | Amiral gemisi (agir donanim) |
| `smollm2:360m` | fallback | 0.4 GB | Edge cihazlar |

> `deepseek-v4-flash/pro`, `kimi-k2.6`, `glm-5.1` gibi **yalnizca Ollama Cloud**'da
> sunulan modeller lokal pull edilemez; canli kesifte "☁ cloud" rozetiyle gorunur.

---

## API Yuzeyi (ozet)

OpenAPI / Swagger: **http://localhost:8080/docs**

### Auth & kullanici
| | |
|---|---|
| `POST /login` | username/password → JWT |
| `POST /api/v1/me/password` | Kendi sifresini degistir |

### Sohbet
| | |
|---|---|
| `POST /api/v1/chat` | One-shot (bekleyip tek seferde donen yanit) |
| `POST /api/v1/chat/stream` | Streaming (NDJSON, token token) |

### Modeller & katalog
| | |
|---|---|
| `GET  /api/v1/models` | Aktif/pasif modeller, canli durumlari |
| `GET  /api/v1/system/catalog` | Birlesik katalog (yaml + override'lar) |
| `POST /api/v1/system/catalog/models` | Yeni model ekle (admin) |
| `DELETE /api/v1/system/catalog/models/{id}` | Override sil (admin) |
| `POST /api/v1/system/catalog/dry-run` | Ekleme oncesi butce/profil raporu |
| `POST /api/v1/system/pull/{model_id}` | Manuel pull tetikle (admin) |
| `POST /api/v1/system/ollama/inspect` | Ollama'dan boyut tahmin et |
| `GET  /api/v1/system/ollama/local` | Yerel Ollama modelleri (admin) |
| `GET  /api/v1/system/discover` | Statik katalogdan onerilen + filtreli modeller |
| `GET  /api/v1/system/discover/remote` | **Canli kesif**: ollama.com + HuggingFace guncel listesi (`?refresh=true` admin ile interneti zorlar) |

### Sistem & profil
| | |
|---|---|
| `GET  /api/v1/system/profile` | Donanim + kapasite + runtime config |
| `GET  /api/v1/system/profiles` | Tum profil tanimlari |
| `GET  /api/v1/system/config` | Mevcut runtime config |
| `PUT  /api/v1/system/config` | Runtime config guncelle (admin) |
| `POST /api/v1/system/replan` | Manuel yeniden plan (admin) |
| `GET  /api/v1/system/resources` | Host CPU/mem/disk + top process + Docker stats |
| `GET  /api/v1/system/bootstrap` | Bootstrap stage stream (token gerekmez) |
| `GET  /api/v1/onboarding/state` | Ilk acilis akisi durumu |

### Denetim, kullanim & KVKK
| | |
|---|---|
| `GET  /api/v1/usage/me` | Kullanicinin kullanim ozeti |
| `GET  /api/v1/usage/global` | Tum kullanim (admin) |
| `GET  /api/v1/audit?limit=100` | Audit log (admin) |
| `GET  /api/v1/users` | Kullanici listesi (admin) |
| `DELETE /api/v1/users/{u}/data` | KVKK silme hakki: islem kayitlarini sil (admin) |
| `DELETE /api/v1/users/{u}` | Hesabi + tum kisisel veriyi sil (admin) |

### Saglik / metrik
| | |
|---|---|
| `GET  /healthz` | Liveness |
| `GET  /readyz` | Readiness (Ollama + aktif modeller) |
| `GET  /metrics` | Prometheus format |

---

## Make komutlari

```bash
make help        # Tum komutlari listele
make preflight   # Port, daemon, disk kontrolu
make up          # preflight + build + up
make up-gpu      # GPU overlay ile
make down        # Durdur (volume korunur)
make restart     # Down + up
make logs        # Canli log akisi
make logs-gw     # Sadece gateway loglari
make logs-ollama # Sadece ollama loglari
make ps          # Container durumlari
make health      # Tum endpoint sağlık kontrolu
make test        # Birim testler (pytest)
make pull-base   # Base image'leri onceden cek
make sim         # Yuk simulatoru calistir
make reset       # Volume dahil her seyi SIL
make clean       # Lokal data sil
make grafana-open / prom-open
```

---

## Alarmlama (Prometheus + Grafana)

`monitoring/rules/ai-gateway.yml` ve `monitoring/grafana/provisioning/alerting/rules.yaml`:

| Alert | Kosul | Severity |
|---|---|---|
| `GatewayDown` | `up{job="gateway"}==0` for 1m | critical |
| `HighErrorRate` | hata orani > %5 for 2m | warning |
| `HighFallbackRate` | fallback orani > %25 for 5m | warning |
| `HighLatencyP95` | p95 > 30 sn for 5m | warning |
| `NoActiveModel` | aktif model sayisi = 0 for 5m | critical |
| `ModelPullStuck` | pull progress > 15 dk asili | warning |
| `HighRateLimit` | rate-limit reddi artiyor | info |

Grafana'da **AI Gateway** klasoru altinda gorulur; Prometheus'ta `/alerts` sayfasinda durum izlenir.

---

## Konfigurasyon (`.env`)

Tum onemli alanlar:

```bash
# Guvenlik
JWT_SECRET=                             # bos birakilabilir: otomatik uretilir (data/jwt_secret)
ADMIN_PASSWORD=admin

# Portlar (cakisma varsa degistir)
GATEWAY_PORT=8080
OLLAMA_PORT=11434
PROM_PORT=9090
GRAFANA_PORT=3000

# Profil ve donanim
CAPACITY_PROFILE=auto                   # auto | lite | balanced | performance
HOST_RAM_GB=                            # bos: otomatik tespit

# Docker resource limit
GATEWAY_MEM_LIMIT=512m
OLLAMA_MEM_LIMIT=6g
GATEWAY_CPU_LIMIT=1.0
OLLAMA_CPU_LIMIT=4.0

# Ollama davranisi (bos: profile gore otomatik)
OLLAMA_KEEP_ALIVE=3m
OLLAMA_NUM_PARALLEL=
OLLAMA_MAX_LOADED_MODELS=
OLLAMA_KV_CACHE_TYPE=f16                # q8_0 icin OLLAMA_FLASH_ATTENTION=true gerekir

# Gateway davranisi
AUTO_PULL_MODELS=false                  # ONERILEN: false
IDLE_UNLOAD_MINUTES=3

# KVKK / uretim
RETENTION_DAYS=180                      # audit/usage kayitlarinin otomatik imha suresi (0=kapali)
DEMO_MODE=true                          # false: sadece admin seed edilir, demo listesi gizlenir

# Canli kesif
DISCOVERY_TTL_HOURS=24                  # uzak katalog cache suresi
DISCOVERY_HF_LIMIT=40                   # HuggingFace'ten cekilecek repo sayisi
```

---

## Klasor yapisi

```
.
├── app/                      # Python paketi
│   ├── main.py               # App kurulumu, middleware, saglik endpointleri
│   ├── runtime.py            # Yasam dongusu: bootstrap, replan, KVKK retention
│   ├── deps.py               # Paylasilan FastAPI dependency'leri
│   ├── routes/               # Is mantigi — odaklanmis router modulleri
│   │   ├── auth_routes.py    #   login + sifre degistirme
│   │   ├── chat_routes.py    #   one-shot + streaming sohbet (cok turlu)
│   │   ├── catalog_routes.py #   katalog, kesif (statik+canli), pull/sil
│   │   ├── system_routes.py  #   profil, kapasite, config, kaynaklar
│   │   ├── users_routes.py   #   kullanim, denetim, KVKK veri haklari
│   │   └── ui_routes.py      #   Jinja2 sayfalari
│   ├── auth.py               # JWT + bcrypt + SQLite (secret otomatik uretimi)
│   ├── capacity.py           # Profil bazli kapasite planlayicisi
│   ├── orchestrator.py       # Model lifecycle (lazy pull, idle unload)
│   ├── ollama_client.py      # HTTP istemci (sync + stream)
│   ├── discovery.py          # Canli kesif: ollama.com + HuggingFace (TTL cache)
│   ├── router.py             # Routing + prompt-aware size
│   ├── hwprobe.py            # Donanim tespiti (CPU/RAM/GPU/disk)
│   ├── sysmonitor.py         # psutil + docker stats
│   ├── audit.py / usage.py   # SQLite + indexler + KVKK purge/silme
│   ├── config.py / models.py # YAML/runtime + Pydantic semalar
│   ├── metrics.py            # Prometheus metrik tanimlari
│   ├── state.py              # AppState + BootstrapTracker
│   ├── ui/
│   │   ├── templates/        # base, login, dashboard, chat, models,
│   │   │                     # onboarding, resources, admin, privacy
│   │   └── static/           # style.css + 8 JS dosyasi
│   └── Dockerfile + requirements.txt
├── config/
│   ├── model_catalog.yaml    # Model + departman + routing kurallari
│   └── default_users.yaml    # Demo seed
├── monitoring/
│   ├── prometheus.yml        # rule_files referansi ile
│   ├── rules/ai-gateway.yml  # Prometheus alert rule'lari
│   └── grafana/provisioning/ # datasources + dashboards + alerting
├── scripts/
│   ├── preflight.sh          # Linux/Mac
│   └── preflight.ps1         # Windows PowerShell
├── simulator/                # Yuk uretici container
├── tests/                    # pytest (capacity, router, auth, usage, config, audit, orchestrator, ollama_client, discovery, kvkk, integration — 100 test)
├── data/                     # Runtime: users.db + audit.db + usage.db
│                             # + runtime_config.yaml + catalog_overrides.yaml
├── docker-compose.yml
├── docker-compose.gpu.yml
├── .env.example
└── Makefile
```

---

## Sorun giderme

| Belirti | Cozum |
|---|---|
| Bilgisayar acilista kilitleniyor | `.env`'de `CAPACITY_PROFILE=lite`, `OLLAMA_MEM_LIMIT=3g`, `AUTO_PULL_MODELS=false` |
| `ollama` saglikli olmuyor | `docker compose logs ollama` — ilk acilis Ollama image (~750 MB) pull eder |
| `8080 portu kullanimda` | `.env`'de `GATEWAY_PORT=9080` gibi degisik bir port verin, `make up` tekrar |
| Gateway 502 donuyor | `/readyz` 503 mu? Model henuz pull edilmemis olabilir, Modeller sayfasindan pull edin |
| GPU goremiyor | `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up` + NVIDIA Container Toolkit |
| Oturumlar restart sonrasi dusuyor | `data/` volume'unu silmeyin (otomatik uretilen `jwt_secret` orada) ya da `.env`'de sabit `JWT_SECRET` verin |
| Canli kesif bos geliyor | Internet erisimi gerekir; offline ortamda statik katalog calismaya devam eder |
| Bootstrap overlay'i her sayfada cikiyor | Tarayici cache temizleyin (Ctrl+Shift+R) |
| RAM yanlis algilaniyor (Docker Desktop) | `.env`'de `HOST_RAM_GB=16` gibi acikca yazin |

---

## Gelistirme

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r app/requirements.txt -r simulator/requirements.txt pytest

# Birim testleri
pytest -q tests/

# Sadece gateway'i rebuild (ollama dokunulmaz)
docker compose up -d --build gateway
```

Tum testler gecmeli — **100 test** (`pytest -q tests/`).

---

## Lisans

MIT. Bitirme projesi olarak ozgurce kullanilabilir.
