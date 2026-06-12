# Inference Hub — Proje Dokumantasyonu

Bu dokuman projenin **ne oldugunu, neden boyle insa edildigini ve nasil calistigini**
tek yerde anlatir: mimari kararlar, teknoloji seciminin gerekceleri, tum API
yuzeyi, model yasam dongusu, kapasite planlamasi ve guvenlik modeli.
Hizli kurulum icin [README](../README.md) yeterlidir; burasi "neden" sorularinin cevabidir.

---

## Icindekiler

1. [Proje ozeti](#1-proje-ozeti)
2. [Teknoloji secimleri ve gerekceleri](#2-teknoloji-secimleri-ve-gerekceleri)
3. [Mimari](#3-mimari)
4. [Donanim farkindaligi ve kapasite planlamasi](#4-donanim-farkindaligi-ve-kapasite-planlamasi)
5. [Model yasam dongusu](#5-model-yasam-dongusu)
6. [Akilli yonlendirme (routing)](#6-akilli-yonlendirme-routing)
7. [API referansi (tum endpointler)](#7-api-referansi-tum-endpointler)
8. [Web arayuzu](#8-web-arayuzu)
9. [Guvenlik ve KVKK](#9-guvenlik-ve-kvkk)
10. [Gozlemlenebilirlik](#10-gozlemlenebilirlik)
11. [DevOps: kurulum, overlay'ler, GPU algilama](#11-devops-kurulum-overlayler-gpu-algilama)
12. [Test stratejisi](#12-test-stratejisi)
13. [Bilincli sinirlamalar ve gelecek isler](#13-bilincli-sinirlamalar-ve-gelecek-isler)

---

## 1. Proje ozeti

**Inference Hub**, kucuk/orta olcekli ekiplerin sirket ici (on-premise) buyuk dil
modeli kullanmasini saglayan bir **LLM gateway**'idir. Temel iddia: *"Kurulacak
makine ne olursa olsun — GPU'suz bir laptop, NVIDIA'li bir is istasyonu, AMD'li
bir sunucu — sistem donanimi kendisi olcer, kendine uygun modelleri secer ve
sifir konfigurasyonla calisir."*

Cozulen problemler:

| Problem | Cozum |
|---|---|
| Veriyi buluta gondermek (KVKK/gizlilik riski) | Tum inference yerel; Ollama portu localhost'a kilitli, dis ag erisimi yok |
| "Hangi model bu makinede calisir?" bilinmezligi | Acilista donanim taramasi + bellek butcesi + tier bazli model onerisi |
| Departman basina farkli ihtiyaclar | Departman + prompt icerigine gore otomatik model secimi |
| Kim neyi sordu, ne kadar kullandi? | Audit (prompt hash'li) + kullanim sayaclari + Prometheus/Grafana |
| Model indirme surecinin opakligi | Canli ilerleme (asama/bayt/hiz/ETA), iptal + yarim dosya temizligi |

---

## 2. Teknoloji secimleri ve gerekceleri

Her secimde olcut ayniydi: **dusuk kaynak ayak izi, sifir harici bagimlilik,
on-premise'de sorunsuz calisma.**

### Backend: FastAPI + Uvicorn (Python 3.12)

- **Neden FastAPI?** Async-first: model pull/inference gibi uzun suren IO islerinde
  tek worker ile cok istemci servis edilir. Pydantic ile istek dogrulama,
  `/docs` (OpenAPI/Swagger) otomatik gelir — API dokumantasyonu elle yazilmaz.
- **Neden Flask/Django degil?** Flask'ta async ikinci sinif; Django bu olcek icin
  agir (ORM, admin, middleware yigini gereksiz). Gateway'in isi IO orkestrasyonu,
  FastAPI tam bu is icin tasarlandi.
- Gateway container'i **512 MB RAM** limitiyle calisir — bilincli olarak hafif.

### Inference motoru: Ollama

- **Neden Ollama?** Tek binary ile model indirme + calistirma + kuantizasyon
  (GGUF/Q4_K_M); CPU'da da GPU'da da ayni API; `hf.co/...` tag'leriyle HuggingFace
  GGUF repolarini dogrudan cekebilme; CUDA **ve** ROCm image'lari hazir.
- **Neden vLLM/TGI degil?** vLLM ve TGI GPU odakli ve kurulumu agir (CUDA zorunlu,
  buyuk image). "GPU'suz laptopta da calismali" hedefi ile celisir. Ollama'nin
  llama.cpp tabani her donanimda calisir.
- Gateway, Ollama'ya **ince bir HTTP istemcisi** (`app/ollama_client.py`, httpx)
  ile konusur; Ollama degisirse degisecek tek dosya budur.

### Frontend: Vanilla JS + Jinja2 (framework'suz)

- **Neden React/Vue degil?** Build zinciri (node_modules, bundler, CI adimi) on-premise
  teslimati agirlastirir. Vanilla JS + tek CSS dosyasi: `docker build` icinde hicbir
  npm adimi yok, image kucuk, hata yuzeyi dar. Sayfa basina bir JS dosyasi
  (`chat.js`, `models.js`, ...) + ortak `common.js` — toplam ~10 dosya.
- Grafikler bagimliliksiz **SVG** ile cizilir (`charts.js`); Chart.js dahi yok.
- Markdown renderer **ev yapimi ve XSS-guvenli**: once tum girdi escape edilir,
  sonra beyaz-listeli etiketler uretilir (`common.js::renderMarkdown`).

### Veri katmani: SQLite + YAML + JSON dosyalari

- **Neden PostgreSQL degil?** Tek-makine kurulumda harici DB islet-me yuku getirir.
  SQLite (audit + usage) WAL modunda bu yuku sifirlar; yedekleme `make backup` ile
  dosya kopyasidir. Olcek ihtiyacinda SQL semasi tasinabilir.
- Model katalogu **YAML** (insan okunur, PR'da diff'lenebilir); kullanici eklemeleri
  ayri `data/catalog_overrides.yaml` katmaninda — orijinal katalog hic kirlenmez.
- Donanim profili `data/hw_profile.json`'a yazilir (yeniden baslatmada cache).

### Gozlemlenebilirlik: Prometheus + Grafana

- Endustri standardi; pull-tabanli oldugu icin gateway'e yuk binmez.
  `prometheus_client` ile native metrik; hazir provisioned Grafana dashboard'u
  ve 7 alert kurali kutudan cikar.

### Dagitim: Docker Compose (+ overlay dosyalari)

- **Neden Kubernetes degil?** Hedef ortam "sirketteki bir makine" — K8s islet-me
  maliyeti amaci asar. Compose + overlay deseni (`gpu` / `rocm` / `tls`) ayni
  `docker-compose.yml`'i bozmadan donanima/ortama gore genisletir.
- **Caddy** (TLS overlay): tek satir config ile ic CA + otomatik sertifika;
  nginx'e gore dramatik olcude az konfigurasyon.

### Kimlik dogrulama: PyJWT + bcrypt

- Stateless JWT (HS256, 8 saat TTL) — session store gerekmez; secret yoksa
  acilista uretilip `data/jwt_secret`'ta kalici saklanir. Parolalar bcrypt.

---

## 3. Mimari

```
                       ┌─────────────────────────── Docker ag (onprem) ───────────────────────────┐
                       │                                                                           │
 Calisan tarayicisi ──►│  :9099  FastAPI Gateway (512 MB)                                          │
 (LAN: http://ip:9099) │  ┌──────────────────────────────────────────────┐                         │
                       │  │ auth.py      JWT + bcrypt + login rate limit │   ┌──────────────────┐  │
                       │  │ router.py    departman+prompt → model secimi │──►│ Ollama (6 GB)    │  │
                       │  │ orchestrator model durum makinesi, pull      │   │ :11434 (yalnizca │  │
                       │  │              kuyrugu, canli telemetri, iptal │   │  127.0.0.1'e     │  │
                       │  │ capacity.py  donanim → profil → butce        │   │  publish edilir) │  │
                       │  │ hwprobe.py   CPU/RAM/GPU (nvidia+amd) kesfi  │   └──────────────────┘  │
                       │  │ audit/usage  SQLite (hash'li prompt, sayac)  │                         │
                       │  │ ui/          Jinja2 + vanilla JS             │                         │
                       │  └──────────────────────────────────────────────┘                         │
                       │        │ /metrics                                                         │
                       │  ┌─────▼──────────┐      ┌──────────────┐                                 │
                       │  │ Prometheus     │─────►│ Grafana :3000│                                 │
                       │  │ (127.0.0.1)    │      └──────────────┘                                 │
                       │  └────────────────┘                                                       │
                       └───────────────────────────────────────────────────────────────────────────┘
```

**Istek akisi (sohbet):**
1. `POST /api/v1/chat/stream` → JWT dogrulama → departman rate limit kontrolu
2. `router.decide()`: prompt analizi (kod blogu? matematik? uzunluk?) + departman
   kurallari → kategori → o kategorideki en uygun hazir model
3. Model indirilmemisse (`AUTO_PULL_MODELS=true` ise): orchestrator pull'u baslatir,
   istemciye **NDJSON `status` olaylari** ile canli indirme ilerlemesi akar
   (asama, %, MB, hiz, ETA); varsayilan ayarda inmemis modele yonlendirme yapilmaz
4. Uretim baslar: token'lar NDJSON olarak akar; bitiste audit + usage + metrik yazilir

**Kod organizasyonu** (is mantigi nerede yasar):

| Dosya | Sorumluluk |
|---|---|
| `app/main.py` | FastAPI app, guvenlik basliklari, healthz/readyz/metrics |
| `app/runtime.py` | Bootstrap (donanim→plan→orchestrator), replan, retention |
| `app/routes/*.py` | HTTP katmani — ince, is mantigi cagirir |
| `app/orchestrator.py` | Model durum makinesi, pull kuyrugu/telemetri/iptal, idle unload |
| `app/router.py` | Yonlendirme kurallari |
| `app/capacity.py` | Profil secimi + bellek butcesi + aktif/pasif model plani |
| `app/hwprobe.py` | CPU/RAM/GPU/disk kesfi (pynvml → nvidia-smi → amdgpu sysfs) |
| `app/discovery.py` | ollama.com + HuggingFace canli katalog (TTL cache) |
| `app/auth.py` / `audit.py` / `usage.py` | Kimlik, denetim, kullanim |

---

## 4. Donanim farkindaligi ve kapasite planlamasi

### Kesif (hwprobe)

Acilista sirayla denenir; ilk basarili kaynak kullanilir:

| Kaynak | Ne bulur |
|---|---|
| `pynvml` (nvidia-ml-py) | NVIDIA GPU adi + VRAM toplam/bos |
| `nvidia-smi` CLI | pynvml yoksa ayni bilgi |
| **`/sys/class/drm` (amdgpu sysfs)** | AMD GPU + VRAM — **ROCm kurulumu gerektirmez** |
| `/proc/meminfo` → psutil | Efektif RAM (Docker Desktop/WSL2 yanlis okursa `HOST_RAM_GB` ile ezilir) |

### Profiller

Donanim olcumu bir **kapasite profiline** cevrilir (`CAPACITY_PROFILE=auto` varsayilan):

| Profil | Otomatik secim kosulu | Bellek butcesi (CPU/GPU) | Davranis |
|---|---|---|---|
| `lite` | <6 GB RAM veya <6 GB VRAM | %25 / %55 | Yalnizca 1 kucuk fallback model |
| `balanced` | 6–16 GB RAM veya 6–12 GB VRAM | %40 / %70 | 2–3 kucuk model, kategori paylasimli |
| `performance` | VRAM ≥ 12 GB GPU | %55 / %80 | Kategori basina model |

Otomatik secimde CPU-only makineler RAM ne olursa olsun en fazla `balanced`
alir; `performance` GPU'suz sistemde yalnizca elle (`CAPACITY_PROFILE=performance`)
secilebilir — GPU'suz buyuk modellerin gecikmesi kullanici deneyimini bozar.

**Coklu model es zamanliligi:** Ayni anda bellekte tutulabilecek model sayisi
(`max_loaded_models`) profil tabaniyla sinirli degildir; **butceyle olceklenir**
(`dynamic_max_loaded`: ~6 GB butce basina +1, tavan 8, profil tabani alt sinir).
Boylece 48 GB VRAM'li bir sunucuda 6, 80 GB'lik bir H100'de 8 model ayni anda
sicak durur — farkli departmanlar farkli modelleri es zamanli kullanir. Ollama
konteyneri de varsayilan `OLLAMA_MAX_LOADED_MODELS=0` (otomatik: GPU basina 3)
ile calisir; `.env`'den sabitlenebilir. Gateway'in es zamanli istek kapisi
(`max_concurrent_requests = min(yuklu, aktif) × paralellik`) ayni planla buyur.

Butceye **sigan** modeller "aktif", sigmayanlar "pasif" isaretlenir; UI bunu
"bellege sigar / sigmaz" rozetiyle gosterir. Model havuzu tier'lidir:
`edge (≤4 GB) → laptop → workstation → datacenter (48 GB+)` — oneriler makinenin
tier'ina gore siralanir.

---

## 5. Model yasam dongusu

### Durum makinesi

```
 unknown ──► queued ──► pulling ──► ready ──► loaded
    ▲           │          │          ▲          │
    │           │          ▼          │          ▼ (idle > IDLE_UNLOAD_MINUTES)
    └── iptal ◄─┘        error ───────┘        ready
  (passive: butceye sigmayan model — istek almaz)
```

- **Varsayilan: kullanici secmeden indirme yok.** Kurulumda hicbir model otomatik
  inmez; indirme admin "Pull et" dediginde (`POST /api/v1/system/pull`) baslar.
  `AUTO_PULL_MODELS=true` yapilirsa (**lazy pull modu**) inmemis bir modele gelen
  ilk sohbet istegi de indirmeyi tetikler ve kullanici ilerlemeyi sohbette canli izler.
- **Sirali kuyruk:** Ayni anda tek pull calisir (disk/ag patlamasin); bekleyenler
  `queued` durumunda gorunur ve iptal edilebilir.
- **Canli telemetri:** Pull sirasinda Ollama'nin katman olaylari toplanip
  asama metni, inen/toplam bayt, **EMA ile yumusatilmis hiz** ve ETA hesaplanir;
  `/api/v1/models` uzerinden UI'a, `/metrics` uzerinden Prometheus'a akar.
- **Iptal:** `DELETE /api/v1/system/pull/{id}` super (veya siradaki) pull'u
  durdurur ve Ollama'ya best-effort delete atar. Yarim kalan `*-partial` blob'lar
  bilerek hemen silinmez: kullanici tekrar denerse Ollama kaldigi yerden devam eder.
- **Kalinti temizligi (blob-janitor):** Compose'taki kucuk `blob-janitor` servisi,
  `STALE_PARTIAL_MAX_AGE_HOURS` (varsayilan 24 saat) yasini asan `*-partial`
  dosyalarini periyodik siler — yarida birakilan indirmeler diskte kalici cop
  birakmaz. Temizligin gateway yerine ayri bir yardimcida yasamasi bilincli:
  gateway Ollama'nin model deposuna **hic dokunamaz** (en az yetki ilkesi) ve
  non-root calistigi icin zaten silme yetkisi yoktur. Docker disinda calisirken
  ayni temizlik `OLLAMA_MODELS_DIR` ayarlanirsa gateway acilisinda da yapilir.
- **Idle unload:** `IDLE_UNLOAD_MINUTES` boyunca istek almayan model RAM/VRAM'dan
  cikarilir (`keep_alive=0`), durumu `ready`'ye doner.

### Bellek yerlesimi: diskte olmak ≠ bellekte olmak

Bir modelin indirilmis (diskte) olmasi onun surekli RAM/VRAM isgal ettigi
anlamina gelmez — Ollama modelleri istek geldikce yukler, keep-alive dolunca
bosaltir. Bu ayrimi gorunur kilan katman:

- **`GET /api/v1/system/memory`** — Ollama'nin `/api/ps` (bellekte oturanlar:
  toplam boyut, VRAM/RAM dagilimi, keep-alive bitisine kalan sure) ve
  `/api/tags` (diskteki boyutlar) ciktilarini gateway'in model durumlariyla
  birlestirir. Ayni cagri **durum senkronu** da yapar: keep-alive dolup model
  kendiliginden bosalmissa `loaded → ready`, dis kanaldan yuklenmisse tersi —
  gosterilen tahmin degil, motorun bildirdigi gercektir.
- **Bellek kokpiti (Genel bakis):** aktif calisan (istek isleyen) / bellege
  yuklenen / bellekte sicak bekleyen / diskte hazir gruplari; model basina
  renkli segmentli butce cubugu; 4 sn'de bir canli (sekme gizliyken durur).
- **Manuel kontrol (admin):** `POST /api/v1/system/models/{id}/load` modeli
  ilk istegi beklemeden bellege isitir (bos prompt'lu generate — uretim ve
  istatistik tetiklemez, arka planda calisir); `POST .../unload` aninda bosaltir.
- **Gozlemlenebilirlik:** `ai_gateway_model_memory_bytes{model,kind=vram|ram}`
  gauge'u ile Grafana'da model basina bellek zaman serisi.

### Indirme ilerlemesinin kullaniciya yansimasi

| Yer | Ne gorunur |
|---|---|
| Modeller sayfasi karti | Ilerleme cubugu + asama ("Model dosyasi indiriliyor") + MB/hiz/ETA, 1.2 sn'de bir canli; iptal butonu |
| Sohbet balonu | Ilk kullanim indirmesinde ayni ilerleme; pull bitince "bellege yukleniyor…" spinner'i |
| Global gosterge | Hangi sayfada olursa olsun sag altta canli kart (tiklayinca Modeller'e goturur) |
| Genel bakis | Model durum tablosu + durum dagilimi grafigi (`queued` dahil) |
| Prometheus | `model_pull_progress{model=...}` gauge + `ModelPullStuck` alarmi |

---

## 6. Akilli yonlendirme (routing)

Karar zinciri (`router.py`):

1. **Admin override:** Admin sohbette belirli bir model sectiyse o kullanilir.
2. **Keyword/yapi kurallari:** Kod blogu/`def`/`import` iceren prompt → `code`;
   matematik/cok adimli akil yurutme isaretleri → `reasoning`.
3. **Departman kurali:** `model_catalog.yaml::departments` — orn. engineering'in
   birincil kategorisi `code`, hr'inki `text`.
4. **Boyut tercihi:** Departmanin `preferred_size` + prompt uzunlugu, ayni
   kategorideki adaylardan kucuk/orta/buyuk secimi belirler.
5. **Fallback zinciri:** Hedef kategoride hazir model yoksa `fallback` kategorisine,
   o da yoksa herhangi bir aktif modele duser; durum yanita `fallback_triggered`
   olarak yazilir (UI rozet gosterir, Prometheus sayar).

Lazy pull modunda (`AUTO_PULL_MODELS=true`) henuz inmemis (`pulling`/`queued`/
`unknown`) modeller de aday olabilir — istek o modeli tetikler, kullanici
indirmeyi canli izler. Varsayilan ayarda yalnizca inmis (`ready`/`loaded`)
modeller aday olur; hicbiri yoksa istek fallback'a duser.

---

## 7. API referansi (tum endpointler)

Tum `/api/v1/*` endpoint'leri `Authorization: Bearer <JWT>` ister (aksi belirtilmedikce).
Interaktif dokumantasyon: **`/docs`** (Swagger) ve **`/redoc`**.

### Kimlik & hesap

| Method | Path | Yetki | Aciklama |
|---|---|---|---|
| POST | `/login` | herkes | Kullanici adi + parola → JWT (8 saat) |
| POST | `/api/v1/me/password` | giris yapmis | Kendi parolasini degistir |

### Sohbet

| Method | Path | Yetki | Aciklama |
|---|---|---|---|
| POST | `/api/v1/chat` | user | One-shot yanit; routing karari + latency + token sayilari ile |
| POST | `/api/v1/chat/stream` | user | NDJSON akisi: `start` → (`status`: indirme ilerlemesi)* → `token`* → `done`; `error` olaylari ayrica |

`status` olayi alanlari: `stage=pull`, `progress` (0–1), `stage_text`,
`completed_mb`, `total_mb`, `speed_mbps`, `eta_seconds`, `status` (pulling/queued).

### Modeller & katalog

| Method | Path | Yetki | Aciklama |
|---|---|---|---|
| GET | `/api/v1/models` | user | Aktif/pasif modeller + canli durum (pull telemetrisi dahil) |
| GET | `/api/v1/system/catalog` | user | Birlesik katalog (YAML + override) |
| POST | `/api/v1/system/catalog/dry-run` | admin | Eklemeden once "hangi profilde sigar?" raporu |
| POST | `/api/v1/system/catalog/models` | admin | Kataloga model ekle (override katmani) |
| DELETE | `/api/v1/system/catalog/models/{id}` | admin | Override'i sil |
| GET | `/api/v1/system/discover` | user | Statik havuzdan donanima uygun oneriler (q/category/tier/max_gb filtreleri) |
| GET | `/api/v1/system/discover/remote` | user | **Canli kesif** — ollama.com + HF guncel listesi (TTL cache; `refresh=true` admin) |
| GET | `/api/v1/system/ollama/local` | admin | Ollama'daki ham yerel model listesi |
| POST | `/api/v1/system/ollama/inspect` | admin | `/api/show` ile parametre/kuantizasyon/boyut tahmini |
| POST | `/api/v1/system/pull/{model_id}` | admin | Indirmeyi baslat (arka planda, canli izlenir) |
| DELETE | `/api/v1/system/pull/{model_id}` | admin | **Suren indirmeyi iptal et** (kalintilar janitor'ca temizlenir) |
| DELETE | `/api/v1/system/models/{model_id}/pulled` | admin | Modeli Ollama'dan sil (disk bosalt; katalog kaydi kalir) |
| GET | `/api/v1/system/memory` | user | Canli bellek yerlesimi: loaded/VRAM/RAM/disk + keep-alive sureleri + toplamlar |
| POST | `/api/v1/system/models/{model_id}/load` | admin | Modeli bellege onceden yukle (warmup, arka planda) |
| POST | `/api/v1/system/models/{model_id}/unload` | admin | Modeli RAM/VRAM'dan cikar (disk kopyasi korunur) |

### Sistem & profil

| Method | Path | Yetki | Aciklama |
|---|---|---|---|
| GET | `/api/v1/system/profile` | user | Donanim + kapasite + runtime config ozeti |
| GET | `/api/v1/system/profiles` | user | Tum profil tanimlari (butce oranlari dahil) |
| GET | `/api/v1/system/config` | user | Mevcut runtime config |
| PUT | `/api/v1/system/config` | admin | Profil/auto_pull/idle sure/kategori atamasi guncelle |
| POST | `/api/v1/system/replan` | admin | Kapasite planini yeniden hesapla |
| GET | `/api/v1/system/resources` | admin | Host CPU/RAM/disk/sicaklik + GPU + top process + container stats |
| GET | `/api/v1/system/bootstrap` | token'siz | Acilis asamalarinin canli durumu (UI splash) |
| GET | `/api/v1/onboarding/state` | user | Ilk kurulum sihirbazi durumu |

### Kullanim, denetim & KVKK

| Method | Path | Yetki | Aciklama |
|---|---|---|---|
| GET | `/api/v1/usage/me` | user | Kendi istek/token/latency ozeti |
| GET | `/api/v1/usage/global` | admin | Tum kullanicilar |
| GET | `/api/v1/audit` | admin | Denetim kayitlari (prompt yalnizca salt'li SHA-256 hash) |
| GET | `/api/v1/users` | admin | Kullanici listesi |
| POST | `/api/v1/users` | admin | Hesap ac (departman/rol) |
| PUT | `/api/v1/users/{username}` | admin | Rol/departman/parola guncelle |
| DELETE | `/api/v1/users/{username}/data` | admin | KVKK silme hakki: islem kayitlarini sil |
| DELETE | `/api/v1/users/{username}` | admin | Hesabi + tum kisisel veriyi sil |

### Saglik & metrik (token'siz)

| Method | Path | Aciklama |
|---|---|---|
| GET | `/healthz` | Liveness (compose healthcheck bunu kullanir) |
| GET | `/readyz` | Readiness — Ollama erisimi + aktif model listesi; degilse 503 |
| GET | `/metrics` | Prometheus exposition format |

---

## 8. Web arayuzu

| Sayfa | Kim | Icerik |
|---|---|---|
| `/ui/login` | herkes | Giris (DEMO_MODE'da demo hesap listesi) |
| `/ui/onboarding` | admin | Ilk acilis: donanim ozeti + onerilen model secimi |
| `/ui/dashboard` | user | Bellek kokpiti (canli RAM/VRAM yerlesimi) + donanim/kapasite/model durumu + SVG grafikler |
| `/ui/chat` | user | Cok turlu sohbet, streaming, markdown, durdur/yeniden uret |
| `/ui/models` | user (aksiyonlar admin) | Katalog + canli kesif + pull/iptal/sil, canli indirme ilerlemesi |
| `/ui/admin` | admin | Profil, kullanici yonetimi, kullanim, denetim |
| `/ui/resources` | admin | Canli CPU/RAM/disk/GPU/sicaklik, container stats |
| `/ui/privacy` | herkes | KVKK aydinlatma metni |

Ortak altyapi: tema (acik/koyu/sistem), mobil drawer, toast'lar, erisilebilirlik
(odak halkalari, `aria-live`, `prefers-reduced-motion`), **global indirme
gostergesi** (her sayfada).

---

## 9. Guvenlik ve KVKK

Detayli envanter: [SECURITY.md](../SECURITY.md). Ozet:

- **Ag yuzeyi:** Yalnizca gateway (9099) LAN'a acilir; Ollama, Prometheus ve
  Grafana varsayilan olarak 127.0.0.1'e kilitlidir (BT ekibi icin
  `GRAFANA_BIND=0.0.0.0` / `PROM_BIND=0.0.0.0` ile acilabilir). TLS icin Caddy
  overlay (`make up-tls`).
- **Kimlik:** JWT HS256 (8 saat) + bcrypt parola + login brute-force limiti
  (`LOGIN_RATE_PER_MIN`, varsayilan 10/dk).
- **Yetki:** `admin`/`user` rolleri; tum yikici islemler admin-only ve audit'e yazilir.
- **Veri minimizasyonu:** Ham prompt sunucuda saklanmaz — audit'te salt'li
  SHA-256 ozeti tutulur; IP toplanmaz; sohbet gecmisi yalnizca tarayicida
  (kullanici bazli localStorage, cikista silinir).
- **Saklama:** `RETENTION_DAYS` (varsayilan 180) sonunda audit/usage otomatik imha.
- **HTTP basliklari:** CSP, X-Frame-Options DENY, nosniff, Referrer-Policy.
- **XSS:** Tum kullanici/model cikti'lari escape edilir; markdown renderer
  beyaz-listeli; CSP inline-script'leri sinirlar.

---

## 10. Gozlemlenebilirlik

- **Metrikler** (`/metrics`): istek sayaclari (model/kategori/departman/durum),
  latency histogramlari, token sayaclari, inflight gauge, fallback/rate-limit
  sayaclari, `model_pull_progress`, yuklu model sayisi, donanim bilgisi.
- **Alarmlar** (`monitoring/rules/ai-gateway.yml`): GatewayDown, HighErrorRate,
  HighFallbackRate, HighLatencyP95, NoActiveModel, **ModelPullStuck**, HighRateLimit.
- **Grafana:** provisioned dashboard (istek hizi, hata orani, latency, token,
  model durumu); anonim erisim varsayilan kapali.
- **Yapisal loglar:** `docker compose logs -f gateway` — bootstrap asamalari,
  plan ozetleri, pull yasam dongusu.

---

## 11. DevOps: kurulum, overlay'ler, GPU algilama

### Compose dosya matrisi

| Dosya | Ne yapar |
|---|---|
| `docker-compose.yml` | Taban: gateway + ollama + blob-janitor + prometheus + grafana (+ sim profili) |
| `docker-compose.gpu.yml` | NVIDIA: her iki container'a `nvidia` device reservation |
| `docker-compose.rocm.yml` | AMD: `ollama/ollama:rocm` image + `/dev/kfd`,`/dev/dri`; gateway'e `/dev/dri` (VRAM okuma) |
| `docker-compose.tls.yml` | Caddy 443 TLS sonlandirma; gateway localhost'a alinir |

### Kurulum akisi (onerilen: `make up` / `scripts\up.ps1`)

```
make up
 ├─ scripts/preflight.sh   port cakismasi, docker daemon, disk, RAM, GPU raporu
 │                         (.env yoksa .env.example'dan uretir)
 ├─ scripts/detect_gpu.sh  nvidia-smi? container toolkit? /dev/kfd?
 │                         → uygun -f overlay listesini secer
 └─ docker compose <secilen dosyalar> up -d --build
```

- Algilama ezilebilir: `GPU_MODE=auto|nvidia|amd|cpu make up`.
- NVIDIA GPU var ama Container Toolkit yoksa: kurulum linkiyle uyari verilir,
  CPU modunda devam edilir (kurulum asla bloke olmaz).
- Windows: `scripts\up.ps1` ayni akisi PowerShell'de yapar (`-GpuMode cpu` destekli);
  AMD ROCm Windows Docker'da desteklenmedigi icin NVIDIA/CPU secenekleri vardir.
- Force hedefler: `make up-gpu` / `up-rocm` / `up-cpu` / `up-tls`.

### Operasyon

| Is | Komut |
|---|---|
| Saglik kontrolu | `make health` (healthz/readyz/ollama/prom/grafana) |
| Loglar | `make logs` / `logs-gw` / `logs-ollama` |
| Yedek / geri yukleme | `make backup` / `make restore` (data/: kullanici DB + audit + config) |
| Yuk testi | `make sim` (cok kullanicili simulasyon, `SIM_*` env'leri) |
| Tam sifirlama | `make reset` (volume'lar dahil) |

---

## 12. Test stratejisi

`tests/` altinda 140+ birim/entegrasyon testi (`make test` veya `pytest -q tests/`):

| Paket | Kapsam |
|---|---|
| `test_orchestrator.py` | Durum makinesi, pull telemetrisi (katman bayt toplama), kuyruk, **iptal + partial temizligi**, stream'de pull olaylari, idle unload |
| `test_router.py` | Kategori/departman/boyut/fallback kurallari |
| `test_capacity.py` | Profil secimi, butce hesabi, aktif/pasif planlama |
| `test_hwprobe_gpu.py` | AMD sysfs kesfi (sahte /sys agaci), vendor raporu |
| `test_auth.py` / `test_users_admin.py` | JWT, bcrypt, rol kapilari, kullanici CRUD |
| `test_audit.py` / `test_usage.py` / `test_kvkk.py` | Hash'li audit, sayaclar, silme hakki, retention |
| `test_discovery.py` | Canli kesif cache/fallback davranisi |
| `test_integration.py` | App seviyesi: login → chat → audit zinciri (sahte Ollama ile) |

Ilke: dis dunyaya (Ollama, internet) giden her sey sahte istemciyle test edilir;
testler ag baglantisiz calisir.

---

## 13. Bilincli sinirlamalar ve gelecek isler

- **Tek makine:** Coklu-node/yuk dengeleme kapsam disi (Compose hedefi). Buyume
  yolunda ayni API ile coklu Ollama backend'i desteklenebilir.
- **In-memory rate limit:** Gateway yeniden basladiginda sayaclar sifirlanir;
  cok-instance kurulumda Redis gerekir (su an hedef degil).
- **JWT revokasyonu yok:** 8 saatlik TTL kabul edilen risk; parola degisiminde
  eski token'lar dolana kadar gecerlidir.
- **Embedding/RAG yok:** Gateway saf sohbet/uretim odakli; dokuman arama ileride
  ayri bir servis olarak eklenebilir.
