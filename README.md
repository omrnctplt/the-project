# Inference Hub

[![tests](https://github.com/omrnctplt/the-project/actions/workflows/test.yml/badge.svg)](https://github.com/omrnctplt/the-project/actions/workflows/test.yml)
[![python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![fastapi](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com/)
[![docker](https://img.shields.io/badge/docker-compose-2496ED.svg)](https://docs.docker.com/compose/)
[![license](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> **Departman bazli, donanima gore kendini ayarlayan, sifir konfigurasyonla tek `docker compose up -d --build` ile ayaga kalkan, on-premise LLM gateway.**

Kucuk ekipler icin Ollama'nin onunde duran bir yonlendirme katmani. Sistem ilk acilista donanimi olcer, uygun **kapasite profilini** secer, **departman + prompt** tabanli akilli yonlendirme yapar, butun istekleri **denetler**. **Canli model kesfi** ollama.com + HuggingFace'ten guncel model listesini otomatik ceker — yeni bir model ciktiginda arayuzu veya katalogu elle guncellemek gerekmez. UI, REST API, Prometheus metrikleri ve Grafana paneli kutudan cikar cikmaz hazirdir.

> 📘 **Derinlemesine dokumantasyon:** Mimari kararlar, teknoloji seciminin gerekceleri, tum API endpoint'leri, model yasam dongusu ve kapasite planlamasi icin **[docs/PROJE.md](docs/PROJE.md)**.

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
- **Bellek kokpiti:** Diskte olmak ≠ bellekte olmak — canli RAM/VRAM yerlesimi (kaynak: Ollama `/api/ps`): aktif calisan / bellekte sicak bekleyen (GPU+RAM dagilimi, keep-alive geri sayimi) / diskte hazir modeller; admin tek tikla **bellege yukle / bellekten cikar**; model basina renkli butce cubugu
- **Tema:** Acik / koyu / sistem temasi — kalici tercih, FOUC'suz on-yukleme
- **Mobil + erisilebilirlik:** Hamburger drawer, dokunmatik uyum, dusuk-guc cihazda efekt kismasi, gorunur odak halkalari, `prefers-reduced-motion`

### Routing & kapasite
- **4 profil:** `lite` (cok dusuk kaynak) / `balanced` (laptop) / `performance` (VRAM ≥ 12 GB GPU) / `auto`
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
- GPU opsiyonel — **NVIDIA ve AMD otomatik algilanir** (asagiya bakin)

### 1. Onerilen yol: `make up` (Linux/macOS) veya `scripts\up.ps1` (Windows)

```bash
make up                                              # Linux / macOS / Git Bash
powershell -ExecutionPolicy Bypass -File scripts\up.ps1   # Windows PowerShell
```

**Neden bu yol?** Iki komut da ayni "anahtar teslim" akisi calistirir:
1. **Preflight:** port cakismasi, Docker daemon, disk, RAM kontrolu — sorun varsa kurulumdan *once* soyler
2. `.env` yoksa otomatik olusturur (`.env.example`'dan)
3. **GPU otomatik algilama:** NVIDIA varsa `docker-compose.gpu.yml`, AMD varsa `docker-compose.rocm.yml` overlay'i kendiliginden eklenir; GPU yoksa CPU modunda devam eder — siz hicbir sey secmezsiniz
4. Compose build + up (gateway, ollama, prometheus, grafana) ve servis URL'lerini yazdirir

Algilamayi ezmek isterseniz: `GPU_MODE=cpu make up` (veya `nvidia` / `amd`;
Windows'ta `scripts\up.ps1 -GpuMode cpu`).

### 2. Alternatif: tek compose komutu

```bash
docker compose up -d --build
```

Calisir — `.env` bile gerekmez (`JWT_SECRET` otomatik uretilir, sistem acilista
donanimi olcup kapasite profilini secer). Ancak bu yol **preflight ve GPU
algilamayi atlar**: GPU'lu makinede CPU modunda kalirsiniz, port cakismasini
compose hatasindan ogrenirsiniz. Bu yuzden varsayilan oneri `make up`'tir.

GPU overlay'lerini elle secmek isterseniz:
```bash
# NVIDIA (NVIDIA Container Toolkit gerekir)
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
# AMD (Linux + amdgpu surucusu; /dev/kfd mevcut olmali)
docker compose -f docker-compose.yml -f docker-compose.rocm.yml up -d --build
```

### GPU destegi matrisi

| Donanim | Linux | Windows (Docker Desktop) |
|---|---|---|
| NVIDIA | ✅ otomatik (`gpu` overlay; Container Toolkit gerekir) | ✅ otomatik (WSL2 GPU destegi acik olmali) |
| AMD | ✅ otomatik (`rocm` overlay; amdgpu surucusu yeterli) | ❌ ROCm Windows Docker'da desteklenmez → CPU |
| GPU yok | ✅ CPU modu | ✅ CPU modu |

Sistem her durumda acilista donanimi olcer (`hwprobe`): VRAM miktarina gore
kapasite profili ve model onerileri otomatik sekillenir. AMD kartlarda VRAM,
ROCm kurulumu gerektirmeden `amdgpu` sysfs arayuzunden okunur. Tuketici AMD
kartlari (RX 6xxx/7xxx) icin gerekirse `.env`'de `HSA_OVERRIDE_GFX_VERSION`
ayarlayin (ornek: RX 6700 XT → `10.3.0`).

### 3. UI'yi ac

| URL | Aciklama |
|---|---|
| **http://localhost:9099** | Inference Hub — login → genel bakis |
| http://localhost:9099/docs | OpenAPI / Swagger |
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

## Sirket aginda erisim (LAN kurulumu)

Sistemi sirketin sunucu odasindaki bir makineye kurdugunuzda, ayni agdaki tum
calisanlar **tarayicidan** erisir — istemci tarafina hicbir kurulum gerekmez.

### 1. Sunucuda kurulum

```bash
git clone <repo> && cd the-project
DEMO_MODE=false ADMIN_PASSWORD='guclu-bir-parola' docker compose up -d --build
```

Gateway varsayilan olarak `0.0.0.0:9099`'i dinler — yani LAN'a aciktir.
Ollama ise bilerek **127.0.0.1**'e baglidir: calisanlar auth/audit katmanini
atlayip dogrudan modele erisemez.

### 2. Sunucunun IP'sini bulun ve guvenlik duvarini acin

```bash
# Linux
hostname -I                          # orn: 192.168.1.40
sudo ufw allow 9099/tcp              # gateway (zorunlu)
sudo ufw allow 3000/tcp 9090/tcp     # Grafana/Prometheus (istege bagli, sadece BT;
                                     # once .env'de GRAFANA_BIND=0.0.0.0 / PROM_BIND=0.0.0.0 gerekir)
```

```powershell
# Windows Server
ipconfig                             # IPv4 adresi
New-NetFirewallRule -DisplayName "Inference Hub" -Direction Inbound -LocalPort 9099 -Protocol TCP -Action Allow
```

### 3. Calisanlara hesap acin

UI → **Ayarlar → Kullanicilar → + Yeni kullanici** (admin). Kullanici adi +
gecici sifre + departman secin; calisan ilk giriste "Sifre degistir" ile kendi
sifresini belirler. Departman, kullanicinin hangi model kategorilerine
erisecegini ve rate limitini belirler.

### 4. Calisanlar baglanir

```
http://192.168.1.40:9099        ←  tek ihtiyaclari olan adres
```

UI'daki Grafana/Prometheus linkleri otomatik olarak ayni sunucu adresine isaret
eder (localhost'a sabitlenmez).

### Guvenlik notlari (uretim)

| Konu | Durum / Oneri |
|---|---|
| **TLS/HTTPS** | Hazir overlay var: `make up-tls` (veya `docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d`). Caddy 443'te kendi ic CA'siyla TLS sonlandirir, gateway portu localhost'a alinir. Sirket CA'niz varsa `deploy/Caddyfile` icinde sertifika yolunu degistirin. |
| `DEMO_MODE` | Uretimde mutlaka `false` — preflight artik acik unutulursa uyarir. |
| `JWT_SECRET` | Bos birakilabilir: sistem guclu bir secret uretip `data/jwt_secret` dosyasinda kalici tutar. |
| `ADMIN_PASSWORD` | Varsayilan `admin` — preflight zayif/eksik parolada uyarir. |
| Prometheus (9090) | **Varsayilan localhost-only** (`--web.enable-lifecycle` auth'suz oldugundan LAN'a acilmaz). Grafana ic agdan erisir; gerekirse `PROM_BIND=0.0.0.0`. |
| Grafana (3000) | Anonim erisim **varsayilan kapali** — `admin / GRAFANA_ADMIN_PASSWORD` ile girilir. Demo icin `GRAFANA_ANONYMOUS=true`. |
| Yedekleme | `make backup` → `backups/inference-hub-data-<tarih>.tgz` (kullanici DB + audit + config). Geri yukleme: `make restore`. |

---

## Mimari

```
                     +----------------------+
                     |   Tarayici / curl    |
                     +----------+-----------+
                                | JWT (Bearer)
                                v
+------------------------------------------------------------+
|                  FastAPI Gateway :9099                     |
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

| Profil | RAM/VRAM butce orani | Max aktif | Max yuklu (bellekte) | Paralel | Kategoriler |
|---|---|---|---|---|---|
| `lite`        | %25 CPU / %55 GPU | 1 | 1 | 1 | fallback |
| `balanced`    | %40 CPU / %70 GPU | 3 | 1+ | 1 | fallback, text, code |
| `performance` | %55 CPU / %80 GPU | 6 | 2-8 | 2 | fallback, text, code, reasoning |

**Coklu model es zamanliligi:** "Max yuklu" sabit degil, **bellek butcesiyle
olceklenir** (~6 GB basina +1 model, tavan 8). Ornek: 48 GB VRAM'li sunucuda 6,
80 GB H100'de 8 model ayni anda bellekte oturur — bir ekip Gemma kullanirken
digeri Qwen kullanir, kimse kimseyi bellekten atmaz. Ollama tarafi da varsayilan
**otomatik** modda calisir (`OLLAMA_MAX_LOADED_MODELS=0` → GPU basina 3 model);
sabitlemek icin `.env`'e sayi yazin.

**Otomatik secim:**
- GPU varsa: VRAM ≥ 12 GB → `performance`, 6-12 GB → `balanced`, < 6 GB → `lite`
- CPU-only: < 6 GB RAM → `lite`, aksi halde `balanced` (GPU'suz `performance`
  yalnizca elle secilebilir — buyuk modeller CPU'da cok yavas kalir)

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
TOKEN=$(curl -s -X POST http://localhost:9099/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' | jq -r .access_token)

curl -X POST http://localhost:9099/api/v1/system/catalog/models \
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

OpenAPI / Swagger: **http://localhost:9099/docs**

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
| `DELETE /api/v1/system/pull/{model_id}` | Suren indirmeyi iptal et — kalintilar otomatik temizlenir (admin) |
| `DELETE /api/v1/system/models/{model_id}/pulled` | Modeli Ollama'dan sil, disk bosalt (admin) |
| `GET  /api/v1/system/memory` | Canli bellek yerlesimi: kim RAM/VRAM'da, kim diskte, keep-alive sureleri |
| `POST /api/v1/system/models/{model_id}/load` | Modeli bellege onceden yukle — warmup (admin) |
| `POST /api/v1/system/models/{model_id}/unload` | Modeli RAM/VRAM'dan cikar, disk kopyasi durur (admin) |
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
make up          # preflight + GPU otomatik algilama + build + up (ONERILEN)
make up-gpu      # NVIDIA overlay'ini zorla
make up-rocm     # AMD (ROCm) overlay'ini zorla
make up-cpu      # GPU olsa bile CPU modunda kur
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
GATEWAY_PORT=9099
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
| `9099 portu kullanimda` | `.env`'de `GATEWAY_PORT=9080` gibi degisik bir port verin, `make up` tekrar |
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
