# Changelog

Tum dikkat ceken degisiklikler bu dosyada listelenir. Format [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) standardina yakindir.

## [0.6.0] - 2026-06-10

Sifir konfigurasyonla tek komut + canli model kesfi.

### Added
- **Canli model kesfi** (`app/discovery.py`) — ollama.com kutuphanesi (~230 model, tum boyut varyantlari) + HuggingFace GGUF API'sinden guncel model listesi; 24 saat TTL'li disk cache (`data/remote_catalog.json`), ag yoksa stale cache'e dusen offline-dostu tasarim. Yeni model ciktiginda UI/katalog guncellemesi gerekmez.
- **`GET /api/v1/system/discover/remote`** — canli katalog endpoint'i: arama, kategori/kaynak/tier filtresi, donanima uygunluk (`fits`, `recommended`) isaretleri, `?refresh=true` (admin) ile aninda guncelleme
- **Modeller sayfasinda "Canli kesif" bolumu** — kaynak (Ollama/HF) ve uygunluk filtreleri, "Listeyi guncelle" butonu, tek tikla **Kur** (katalog + indirme tek adim)
- **JWT_SECRET otomatik uretimi** — env verilmezse guvenli secret uretilir ve `data/jwt_secret` dosyasinda kalici saklanir; `.env` dosyasi olmadan `docker compose up -d --build` tek basina calisir
- **Login brute-force korumasi** — kullanici basina dakikada 10 deneme (429 + `Retry-After`)
- **Pull ilerleme gostergesi** — indirme surerken kartta yuzde rozeti + 4 sn'de bir otomatik yenileme
- **RAM tahmin motoru** — parametre sayisindan Q4_K_M kalibrasyonlu bellek tahmini; HF sharded GGUF repolari (Ollama desteklemiyor) otomatik elenir
- 13 yeni test (`tests/test_discovery.py`): parse, RAM tahmini, cache TTL, offline fallback, endpoint entegrasyonu (68 -> 87)

### Fixed
- **Donanim RAM tespiti** — gateway'in kendi 512 MB container limiti "efektif RAM" sanilip sistemi her zaman `lite` profile dusuruyordu; oncelik artik `HOST_RAM_GB > /proc/meminfo > psutil`, cgroup limiti yalnizca bilgi amacli raporlanir
- discover'da butce tamamen doluyken (`budget_free=0`) modeller yanlislikla "sigiyor" gorunuyordu
- `persona` kategorisi API semasina eklendi (UI listeliyordu ama API kabul etmiyordu)
- Replan sonrasi eski idle-sweep gorevleri iptal edilmeden birikiyordu (task sizintisi)
- HF tag'lerinden uretilen `model_id` 64 karakter sinirina ve `/` karakterine uygun normalize edilir

### Changed
- `docker-compose.yml`: `JWT_SECRET` artik zorunlu degil (`:?` kaldirildi)
- `.env.example` ve preflight mesajlari otomatik secret uretimini yansitir

## [0.5.0] - 2026-06-03

Donanim-farkindalikli dinamik model havuzu + admin kategori yonetimi.

### Added
- **Donanima gore dinamik oneri** — `edge / laptop / workstation / datacenter` tier'lari; discover endpoint donanima gore onerir (laptop'ta kucuk modeller, H100/H200'de dev modeller)
- **Guncel & kapsamli model havuzu** — 41 model: Qwen3, Llama 4 (Scout/Maverick), DeepSeek-V3/R1, Gemma 3, Phi-4, Mistral, Mixtral, Kimi, SmolLM3, gpt-oss, IBM Granite... her birinde tier + kaynak + lisans
- **Persona / rol yapma kategorisi** — routing kurali + katalog + departman destegi
- **Admin kategori → model atamasi** — her amac (kod/metin/reasoning/persona) icin model secimi; router bu atamaya oncelik verir
- **HuggingFace model destegi** — `hf.co/...` GGUF tag'leri ile tek-tik ekleme + pull; kaynak otomatik isaretlenir
- **Ollama'dan gercek silme** — disk bosaltan kaldirma endpoint'i (`DELETE /api/v1/system/models/{id}/pulled`) + UI
- **Model kaynak gorsellestirme** — kart basina butce-payi cubugu, tier ve kaynak (HF) rozetleri

### Changed
- discover endpoint statik liste yerine katalog havuzundan **tier-farkindalikli** uretir
- Kategori onceligi `persona`'yi da kapsar; performance profili persona modellerini aktif edebilir

### Fixed
- Statik varlik cache-busting surum bump'i ile dogru calisir (`?v=0.5.0`)

## [0.4.0] - 2026-06-03

UX/UI olgunlasmasi + dayaniklilik (resilience) iyilestirmeleri.

### Added
- **Sohbet markdown render** — kod blogu (kopyala butonlu), liste, baslik, kalin/italik, link; bagimliliksiz, XSS'siz renderer
- **Streaming kontrolleri** — Durdur (AbortController ile iptal), yaniti kopyala, yeniden uret; canli `tok/s` hiz gostergesi
- **Tema sistemi** — acik / koyu / sistem; FOUC'suz on-yukleme, kalici tercih, `prefers-color-scheme` takibi
- **Erisilebilirlik** — gorunur odak halkalari (`:focus-visible`), `aria-current`, `prefers-reduced-motion` ile hareket azaltma
- **Mobil drawer** — hamburger menu + backdrop; sohbet mobilde tek kolon; dusuk-guc cihaz tespiti ile efekt kisma
- **Dashboard grafikleri** — bagimliliksiz SVG: bellek butcesi donut'u, model durumu ve kullanim barlari + skeleton shimmer
- **Statik varlik cache-busting** — `?v=<surum>` ile surum atlamalarinda bayat JS/CSS sorunu onlenir
- **HTTP guvenlik basliklari** — CSP, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy` (middleware); `/docs` Swagger CDN icin CSP disinda; rate-limit 429'da `Retry-After`
- **Chat verimliligi** — yaraticilik (temperature) secici, markdown disa aktar, `Ctrl/Cmd+Shift+O` yeni-sohbet kisayolu, streaming `aria-live`
- **Test kapsami genisletildi** — auth, usage/rate-limit, config, audit, orchestrator, ollama_client + uctan uca endpoint & guvenlik testleri (16 -> 68)

### Fixed
- **Streaming gecikmesi** — `chat/stream` isteklerinde usage + audit'e 0 yerine gercek `latency_ms` yaziliyor
- **Versiyon tutarliligi** — tek kaynak (`app.__version__`); FastAPI, UI ve API tum yuzeylerde senkron
- **Donanim profili yolu** — `hw_profile.json` artik `DATA_DIR`'e yaziliyor (eskiden sabit `/data`)
- **Starlette `TemplateResponse`** — guncel imza (deprecation uyarisi giderildi)

## [0.3.1] - 2026-05-20

### Added
- **GitHub Actions CI** (`.github/workflows/test.yml`) — her push'ta pytest + Docker compose syntax + gateway image smoke test
- **LICENSE** dosyasi (MIT)
- **`.gitattributes`** — LF/CRLF normalize (Windows + Linux/Mac calisanlar arasinda uyari yok)
- **README badge'leri** — tests, python, fastapi, docker, license

## [0.3.0] - 2026-05-20

Buyuk UI/UX overhauli + DevOps-grade tooling.

### Added
- **Sidebar layout** — tum sayfalar tutarli sol nav (Sohbet / Genel Bakis / Modeller / Ayarlar / Kaynaklar)
- **Onboarding sihirbazi** (`/ui/onboarding`) — ilk acilista donanim ozeti + kategoriye gore filtreli model kartlari, yesil cerceveli olanlar butceye sigar
- **ChatGPT-tarzi sohbet** — sol konusma listesi, sticky textarea, streaming cursor (▌), departman bazli ornek prompt kartlari, localStorage'da gecmis
- **Modeller sayfasi** (`/ui/models`) — arama + kategori/durum filtresi + accordion + model kartlari (Pull / Sil / Hizli test), "+ Yeni model ekle" modal'i (inspect + dry-run + ekle)
- **Sistem kaynaklari** (`/ui/resources`, admin) — host CPU/mem/disk + canli progress bar, top 8 process tab'lari, Docker container stats, otomatik aksiyon onerileri
- **Yonetim** (`/ui/admin`) — 4 sekme: Calisma profili / Kullanicilar / Kullanim / Denetim + sifre degistirme modal
- **Bootstrap stage stream** — 7 adim (schema, users, hw, catalog, plan, orch, local_scan) canli overlay; sadece backend ready=false oldugunda goronur
- **Dinamik model discovery** — `/api/v1/system/discover` endpoint'i + Gemma 4 (E2B/E4B), Qwen3 (0.6B-8B), Phi-4 (mini + 14B), DeepSeek-R1 (1.5B-14B), DeepSeek V3 pruned, Mistral 7B / Small 3.2, Llama 3.3 70B, Granite 3.1, SmolLM2 360M
- **Departman resource_class** + **preferred_size** — `light`/`medium`/`heavy` × `small`/`medium`/`large`, router prompt-aware boyut secimi
- **Catalog dry-run** — model eklemeden once 4 profilde butce + kategori uygunlugu raporu
- **Streaming chat** — `/api/v1/chat/stream` NDJSON akisi (token-by-token)
- **Sifre degistirme** — `/api/v1/me/password` + UI modal
- **Sistem kaynak izleme** — `app/sysmonitor.py` (psutil host stats + docker stats + auto-action)
- **Port preflight** — `scripts/preflight.sh` (Linux/Mac) + `.ps1` (Windows): port cakismasi, Docker daemon, disk, RAM kontrolu
- **Makefile** — `make up/down/restart/logs/health/test/reset/sim` + GPU varyasyonu
- **Grafana alert** — 7 alert rule: GatewayDown, HighErrorRate, HighFallbackRate, HighLatencyP95, NoActiveModel, ModelPullStuck, HighRateLimit
- **Prometheus rule_files** — `monitoring/rules/ai-gateway.yml`

### Changed
- **Kapasite plani profil bazli yeniden tasarlandi** — CPU butce orani %75'ten %25-55'e dustu, kategori basina en kucuk model seciliyor (eskiden bos butceye butun modeller yukleniyordu)
- **Otomatik pull KAPALI** (default) — kullanici secinceye kadar disk ve ag yuku sifir
- **Bootstrap overlay duzeltildi** — sessionStorage flag ile sadece backend ready=false oldugunda goronur, sayfalar arasinda flash yok
- **Routing tutarliligi** — `GET /` token varsa `/ui/dashboard`'a, yoksa `/ui/login`'e
- **Chat sayfasi** app-shell sidebar'i koruyor (eskiden tamamen ayri layout idi)
- **README** baştan yazildi — production-grade tanitim, API tablosu, mimari diyagram, sorun giderme

### Fixed
- Docker resource limit'leri (gateway 512m, ollama 6g default)
- Default `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_MAX_LOADED_MODELS=1` — eskiden 2/3 idi, swap'a iniyordu
- Idle unload default 3 dk (eskiden 10 dk)
- `HOST_RAM_GB` env override desteği (Docker Desktop / WSL2 icin)

## [0.2.0] - 2026-05-19

- Profil bazli kapasite (lite/balanced/performance)
- Streaming chat + dinamik katalog + Grafana alerts
- Sifre degistirme endpoint

## [0.1.0] - 2026-05-18

- Ilk iskele: FastAPI gateway, Ollama integration, JWT auth, departman routing, Prometheus + Grafana, docker-compose
