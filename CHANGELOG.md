# Changelog

Tum dikkat ceken degisiklikler bu dosyada listelenir. Format [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) standardina yakindir.

## [0.12.0] - 2026-06-12

Ingilizce dil destegi + GPU'yu sonradan etkinlestirme rehberi.

### Added
- **Ingilizce arayuz (i18n)** — kenar cubugunda TR/EN dil anahtari; tercih kalici (`hub_lang`). Hafif altyapi: Turkce kaynak metin anahtar, `i18n.js` sozlugu EN'e cevirir (`t()` + `data-i18n`); 430+ ceviri girdisiyle tum sayfalar kapsanir (sohbet, modeller, bellek kokpiti, ayarlar, kaynaklar, kurulum sihirbazi, giris). KVKK aydinlatma metni hukuki dokuman oldugundan Turkce kalir; backend API mesajlari kapsam disidir (dokumante edildi)
- **README "GPU'yu sonradan etkinlestirme"** — sil-kur gerekmedigi (volume'lar korunur, `make up` yerinde yukseltir), NVIDIA Container Toolkit kurulum komutlari (Linux), Docker Desktop/WSL2 notu (Windows), AMD `/dev/kfd` on kosulu

## [0.11.0] - 2026-06-12

Coklu model es zamanliligi + tam yonetim ozgurlugu: kesif kartlarindan da iptal/kaldirma.

### Added
- **Coklu model es zamanliligi** — `max_loaded_models` artik bellek butcesiyle olcekleniyor (`dynamic_max_loaded`: ~6 GB basina +1 model, tavan 8; profil tabani alt sinir). 48 GB VRAM → 6, 80 GB → 8 model ayni anda bellekte; compose'ta `OLLAMA_MAX_LOADED_MODELS`/`OLLAMA_NUM_PARALLEL` varsayilani 0 (Ollama otomatigi: GPU basina 3 model) — eski sabit `1` kilidi kaldirildi
- **Kesif kartlarinda tam yasam dongusu yonetimi** — canli kesif (ollama.com/HF) kartlari artik gercek model durumunu gosterir: indirme sirasinda ilerleme cubugu + "Indirmeyi iptal et", kuruluysa "Hizli test" + "Diskten kaldir" (eskiden yalnizca "Sistemde kurulu" yaziyordu, yonetim icin katalog bolumune donmek gerekiyordu)
- **Global indirme gostergesinde iptal** — sag alttaki canli kartta admin'e tek tik "Iptal et" (sayfa degistirmeden)

### Changed
- **Web arayuzu varsayilan host portu 7070 → 8888** — 7070 AnyDesk'le, 9090 Prometheus'la cakisiyor; 8888 sade ve akilda kalir. Container ici port 7070 olarak kalir (`GATEWAY_PORT` ile host tarafi serbestce degistirilebilir)
- **"Ollama'dan sil" → "Diskten kaldir"** — eylemin ne yaptigi etiketten anlasilir

## [0.10.0] - 2026-06-11

Bellek kokpiti: "diskte olmak" ile "bellekte olmak" ayrimi artik tek bakista — sistem gercek anlamda yonetilebilir.

### Added
- **Bellek kokpiti (Genel bakis)** — canli RAM/VRAM yerlesimi, 4 sn'de bir guncellenir (sekme gizliyken durur). Gruplar: *aktif calisiyor* (istek isleyenler, canli nabiz), *bellege yukleniyor*, *bellekte hazir/sicak* (GPU+RAM dagilimi ve keep-alive geri sayimi: "~2 dk sonra otomatik bosalir"), *diskte hazir (bellekte degil)*; alt notta indirilmemis katalog modelleri ve **katalog disi Ollama modelleri** (boyutlariyla)
- **Bellek butcesi cubugu** — yuklu her model ayri renk segmenti; ayrilan butceye karsi gercek doluluk
- **`GET /api/v1/system/memory`** — Ollama `/api/ps` + `/api/tags` birlesimi: model basina loaded/vram_bytes/ram_bytes/disk_bytes/expires_in_seconds + toplamlar + butce; gateway'in model durumunu Ollama gercegiyle senkronlar (keep-alive dolup model kendiliginden bosalmissa `loaded → ready`)
- **Bellege yukle / bellekten cikar** — `POST /api/v1/system/models/{id}/load` (arka planda warmup; ilk istegi beklemeden hazir tutar) ve `POST .../unload` (aninda RAM/VRAM bosaltir, disk kopyasi durur); kokpitte tek tik admin butonlari
- **`ai_gateway_model_memory_bytes` metrigi** — model basina vram/ram dagilimi Prometheus'a; Grafana'da bellek zaman serisi cizilebilir

## [0.9.0] - 2026-06-11

Model indirme/yukleme her an gorunur: arayuz hicbir asamada "donmus" gibi durmaz.

### Added
- **Canli indirme telemetrisi** — orchestrator artik pull sirasinda asama (manifest/katman/dogrulama), inen/toplam bayt, anlik hiz (MB/s) ve tahmini kalan sure (ETA) tutar; `/api/v1/models` bu alanlari dondurur
- **Modeller sayfasinda canli ilerleme karti** — indirilen modelin kartinda ilerleme cubugu + asama + boyut + hiz + ETA; 1.2 sn'de bir yerinde guncellenir (tam sayfa yenileme yok), bitince/hata olunca toast bildirimi
- **Sohbette indirme gorunurlugu** — ilk kullanimda model indiriliyorsa yanit balonunda canli ilerleme cubugu gosterilir (streaming'de sunucudan `status` olaylari, one-shot'ta arka plan yoklamasi); model bellege yuklenirken "Model hazirlaniyor…" donen gosterge
- **Global indirme gostergesi** — hangi sayfada olunursa olunsun suren indirme sag altta canli kartla gorunur; tiklayinca Modeller sayfasina goturur
- **`queued` model durumu** — indirme sirasi bekleyen model artik "sirada" olarak etiketlenir (eskiden sessizce bekliyordu)
- **Indirme iptali** — `DELETE /api/v1/system/pull/{id}`: suren veya siradaki indirme guvenle durdurulur (Modeller sayfasinda "Indirmeyi iptal et" butonu); tekrar denenirse Ollama kaldigi yerden devam eder
- **blob-janitor servisi** — yarim kalan indirmelerin `*-partial` blob kalintilarini `STALE_PARTIAL_MAX_AGE_HOURS` (24 sa) sonra otomatik siler; gateway'e Ollama deposuna yazma yetkisi verilmez (en az yetki + non-root uyumu)
- **GPU otomatik algilama (NVIDIA + AMD)** — `make up` artik nvidia-smi/Container Toolkit ve `/dev/kfd` kontrolu yapip dogru overlay'i kendisi secer (`scripts/detect_gpu.sh`, `GPU_MODE=auto|nvidia|amd|cpu`); yeni `docker-compose.rocm.yml` AMD overlay'i; `hwprobe` AMD VRAM'i ROCm gerektirmeden amdgpu sysfs'ten okur; Windows icin tek komut kurulum `scripts\up.ps1`
- **Hata durumunda kurtarma** — model kartinda hata rozeti uzerine gelince sebep gorunur, "Tekrar dene" tek tikla yeniden indirir
- **`docs/PROJE.md`** — mimari kararlar, teknoloji gerekceleri, tum API endpoint'leri, model yasam dongusu ve DevOps akisini anlatan kapsamli proje dokumani (README'den linkli)

### Changed
- **Web arayuzu varsayilan portu 8080 → 7070** — gateway, compose, TLS overlay, Caddy, Prometheus, preflight, simulator, Makefile ve dokumantasyon dahil tum katmanlarda guncellendi (`GATEWAY_PORT` ile degistirilebilir)
- **README kurulum bolumu** — onerilen yol artik `make up` / `scripts\up.ps1` (preflight + GPU algilama + .env uretimi); tek compose komutu alternatif olarak korunur, GPU destegi matrisi eklendi
- **`make up-rocm` / `make up-cpu`** — overlay'i zorlamak icin yeni hedefler; `make up-tls` artik preflight + GPU algilama da yapar
- **Replan indirmeleri kesmiyor** — config/katalog degisikligi (replan) suren indirmeleri duzgun durdurup yeni orchestrator'da kaldigi yerden devam ettirir (eskiden indirme sessizce olur, iptal edilemez hale gelirdi); ayrica replan artik `AUTO_PULL_MODELS=false` iken seed model indirmez ("kullanici secmeden indirme yok" sozlesmesi her yolda gecerli)
- **Grafana varsayilan localhost-only** — Prometheus ile ayni guvenlik durusu; LAN'a acmak icin `GRAFANA_BIND=0.0.0.0`

### Fixed
- **`/api/v1/system/resources` admin'e kilitlendi** — host process listesi/container istatistikleri artik yalnizca admin'e gorunur (dokumantasyonun vaat ettigi davranis)
- **Dashboard model tablosunda XSS** — `ollama_tag` escape edilmeden basiliyordu; ayrica `ollama_tag` API seviyesinde karakter desenine baglandi
- **Sohbet one-shot bekleme gostergesi** — gec gelen yoklama yaniti tamamlanmis cevabin uzerine yazamaz; ilgisiz bir indirme artik "sizin modeliniz" gibi sunulmaz (notr metin)
- **Modeller sayfasi canli yoklamasi** — durum gecisi sirasindaki tek API hatasi ilerleme guncellemesini kalici durduramaz

## [0.8.0] - 2026-06-10

Sirket ici (LAN) kurulum paketi: kullanici yonetimi + ag guvenligi sertlestirmesi.

### Added
- **Admin kullanici yonetimi** — Ayarlar → Kullanicilar: yeni calisan hesabi acma (departman/rol secimi), sifre sifirlama, departman/rol duzenleme, hesap silme; tum islemler audit'e yazilir (`POST/PUT /api/v1/users`)
- **TLS overlay** — `make up-tls`: Caddy 443'te ic CA ile HTTPS sonlandirir, gateway portu localhost'a alinir (`docker-compose.tls.yml` + `deploy/Caddyfile`)
- **README "Sirket aginda erisim (LAN)"** — sunucu IP, firewall (ufw/Windows), calisan hesabi acma, port matrisi ve guvenlik tablosu
- **`make backup` / `make restore`** — `data/` (kullanici DB + audit + config) tarihli arsiv + geri yukleme
- **Preflight uretim kontrolleri** — DEMO_MODE acik ve ADMIN_PASSWORD zayifsa uyari (sh + ps1)

### Changed
- **Prometheus varsayilan localhost-only** — `--web.enable-lifecycle` auth'suz oldugundan LAN'a kapatildi (Grafana ic agdan erisir; `PROM_BIND=0.0.0.0` ile acilabilir)
- **Grafana anonim erisim varsayilan kapali** — `GRAFANA_ANONYMOUS=true` ile demo modu
- **UI izleme linkleri host-bagimsiz** — Grafana/Prometheus linkleri `location.hostname` uzerinden uretilir; LAN'dan giren calisanlarda artik kirilmaz
- **Login brute-force limiti yapilandirilabilir** — `LOGIN_RATE_PER_MIN` env (varsayilan 10/dk)

### Fixed
- **CPU sicaklik fallback'i disk sensorunu atlar** — sogutucusuz NVMe (85-95°C) CPU degeri sanilip sahte "asiri isinma" uyarisi uretebiliyordu
- **Sicaklik test paketi sertlestirildi** — `/sys/class/thermal` govde + baglanti testleri, ayirt edici sensor onceligi, 89.9/90.0 esik siniri, disk-atlanir fallback (131 test)

## [0.7.2] - 2026-06-10

### Added
- **Her kaynaga sicaklik gostergesi** — CPU, disk ve GPU kartlarinin kosesinde renk kodlu yarim-daire SVG gauge (yesil < 60° / amber 60-79° / kirmizi >= 80°, disk icin 50/65; kritik seviyede nabiz animasyonu). Sensor yoksa gosterge gizlenir (donanim-farkindalik ilkesi)
- **CPU + disk sicaklik toplama** — `psutil.sensors_temperatures` (coretemp/k10temp/nvme/drivetemp...) + `/sys/class/thermal` fallback'i; Windows gelistirme ortaminda zarifce None
- **CPU asiri isinma onerisi** — >= 90°C'de otomatik aksiyon karti (thermal throttling uyarisi)

### Fixed
- Kaynaklar cevrimdisi banner'i tanimsiz `--error` yerine `--danger` rengini kullanir (gorunmeyen kenarlik)

## [0.7.1] - 2026-06-10

### Added
- **Canli GPU izleme** — Kaynaklar sayfasinda GPU basina VRAM kullanimi, GPU yuku, sicaklik ve guc karti (pynvml; yoksa nvidia-smi); VRAM > %90 ve sicaklik >= 85°C icin otomatik aksiyon onerileri; GPU yoksa bolum gizli kalir
- **GPU overlay genisletildi** — `docker-compose.gpu.yml` artik gateway'e de GPU erisimi verir (dogru donanim tier'i + canli metrikler)
- **Cloud modeller kesifte** — DeepSeek-V4, Kimi-K2.x, GLM-5.x gibi yalnizca Ollama Cloud modelleri "☁ cloud" rozetiyle listelenir (on-prem kurulamaz, veri disari cikar uyarisiyla)
- **Katalog 2026 Q2 yenilemesi** — 59 model: Gemma 4 (5 boyut), Qwen3.5 (0.8B-122B), Qwen3.6, Granite 4.1, Nemotron 3 + Cascade-2, Mistral Medium 3.5, LFM2.5
- **Login guvenilirligi** — DEMO_MODE'da demo parolalar her acilista tabloya esitlenir; tikla-doldur demo tablosu; kullanici adi trim

### Changed
- Kullaniciya gorunen "butce" ifadeleri "bellek butcesi / bellege sigar" olarak netlestirildi
- Canli kesif istemcisi tam listeyi ceker (limit=1000) — tum modeller aranabilir

## [0.7.0] - 2026-06-10

KVKK uyum paketi + UX olgunlasmasi + mimari sadelestiriilme (anahtar teslim surumu).

### Added — KVKK / guvenlik
- **Aydinlatma metni sayfasi** (`/ui/privacy`, KVKK m.10) — login ekranindan ve kenar cubugundan erisilir; giris formu acik atif icerir
- **Veri saklama suresi** — `RETENTION_DAYS` (varsayilan 180 gun): gunluk arka plan gorevi suresi dolan audit/usage kayitlarini otomatik siler
- **Silme hakki (m.7/m.11)** — `DELETE /api/v1/users/{u}/data` (islem kayitlarini sil) ve `DELETE /api/v1/users/{u}` (hesabi tamamen sil); her ikisi denetim kaydina islenir
- **DEMO_MODE** — `false` yapildiginda yalnizca admin seed edilir ve login ekranindaki demo parola listesi gizlenir (uretim modu)
- **Ollama portu kilitlendi** — `127.0.0.1` bind: agdaki istemciler gateway'in auth/audit katmanini atlayamaz
- **Audit hash'ine kurulum-bazli salt** — bilinen-metin eslestirme saldirisina karsi
- **Parola politikasi** — yeni parolalar en az 8 karakter
- **SECURITY.md** — veri envanteri, KVKK onlemleri, uretim sikilastirma rehberi

### Added — UX
- **Cok turlu sohbet** — onceki turlar artik modele baglam olarak gidiyor (`history` alani, karakter butceli); sohbet gercekten "konusma" oldu
- **Sohbet gizliligi** — konusmalar kullanici-bazli anahtarda saklanir, cikista tamamen silinir (ortak bilgisayar guvenligi)
- **Rol-farkindalikli UI** — admin olmayanlar icin kurulum/silme butonlari gizlenir (403 suprizi yok), /ui/admin ve /ui/resources panele yonlendirir, onboarding bilgilendirme ekranina doner
- **Modal sistemi yenilendi** — dogrulama hatasinda acik kalir (veri kaybolmaz), Escape/focus-trap/aria-modal destegi; tum native confirm/alert'ler tema uyumlu modala tasindi
- **Akilli kaydirma** — stream sirasinda kullanici yukari kaydirdiysa zorla dibe cekilmez
- **Akis sirasinda sohbet degistirme korumasi** — token'lar yanlis sohbetin uzerine yazilmaz
- **Dokunmatik erisim** — hover-gizli butonlar (sohbet sil, kopyala) dokunmatik cihazda gorunur
- **Kaynaklar sayfasi dayanikliligi** — baglanti kopunca tek banner + 20 sn'ye yavaslayan yeniden deneme (toast yagmuru yok)
- **Skeleton yukleme** — modeller sayfasi ilk acilista iskelet kartlar gosterir
- **Klavye erisilebilirligi** — akordeon basliklari Tab/Enter/Space ile kullanilabilir (aria-expanded)
- **Onboarding mukerrer kayit bug'i** — model_id artik katalogdaki gercek id'den alinir (ayni model iki farkli id ile eklenemez)

### Changed — mimari
- **main.py monoliti bolundu** (1130 satir → ~150): is mantigi `app/routes/` altinda 6 odakli modul (auth, chat, catalog, system, users, ui); yasam dongusu `app/runtime.py`; paylasilan dependency `app/deps.py` — `app.main:app` giris noktasi degismedi
- **Chat kod tekrari kaldirildi** — `/chat` ile `/chat/stream` arasindaki ~55 satirlik kopya (rate-limit + routing karari) tek `_decide`/`_enforce_ready_and_rate` yardimcisina indi
- **Olu kod temizligi** — `warmup_all`, `hwprobe.load_profile`, `BootstrapTracker.all_done`, okunmayan `warmup_on_start` anahtari; `ChatStreamRequest` artik `ChatRequest`'ten kalitim alir
- 13 yeni KVKK testi (87 → 100)

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
