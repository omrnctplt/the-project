# Changelog

Tum dikkat ceken degisiklikler bu dosyada listelenir. Format [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) standardina yakindir.

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
