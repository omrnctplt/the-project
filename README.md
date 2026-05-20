# On-Premise AI Gateway

Kucuk ekipler icin departman bazli, hafif ve acik kaynak bir yerel LLM yonlendirme katmani. Tek `docker compose up` ile gateway, Ollama, Prometheus ve Grafana ayaga kalkar. Sistem ilk acilista donanimi olcer, **uygun kapasite profilini secer**, departman + keyword tabanli akilli yonlendirme yapar ve butun istekleri denetler.

> **Bitirme projesi notu:** Bu repository, departmana gore otomatik model secimi, denetlenebilir kullanim kaydi ve dinamik kapasite planlamasi yapan bir kavram kanitidir. Buyuk kurumsal cozumlerle (Run:ai, KServe, Ray Serve) yarisma iddiasinda degildir; 5-50 kisilik ekiplere "her seyin tek bir Docker projesine sigmasi" gozeten bir alternatif sunar.

---

## Mimari

```
        +---------------------+
        |   Tarayici / Curl   |
        +----------+----------+
                   | JWT
                   v
+----------------------------------------+
|       FastAPI Gateway (port 8080)      |
|  - Login & rol/departman cikarimi      |
|  - Rate limit (departman basina)       |
|  - Router (departman + keyword kural.) |
|  - Orchestrator (lazy pull, throttle)  |
|  - Capacity planner (profil bazli)     |
|  - Audit & Usage (SQLite)              |
|  - Prometheus /metrics                 |
+--------+---------------+----------+----+
         |               |          |
         v               v          v
   +-----------+   +-----------+  +----------+
   |  Ollama   |   |Prometheus |  | Grafana  |
   |  :11434   |   |  :9090    |  | :3000    |
   +-----------+   +-----------+  +----------+
        |
        v
  (model storage / VRAM-RAM)
```

---

## Hizli Baslangic

### Gereksinimler
- Docker Engine veya Docker Desktop (Windows / Linux / macOS)
- En az 6 GB RAM, 20 GB disk (lite profil 4 GB ile de calisir)
- GPU opsiyonel — yoksa modeller CPU'da calisir

### 1. Ortam degiskenlerini hazirla
Windows PowerShell:
```powershell
Copy-Item .env.example .env
notepad .env   # JWT_SECRET ve ADMIN_PASSWORD'u guclu degerlerle degistirin
```
Linux/macOS:
```bash
cp .env.example .env
${EDITOR:-nano} .env
```

`.env` icindeki onemli alanlar:
- `CAPACITY_PROFILE`: `auto` (onerilen) / `lite` / `balanced` / `performance`
- `HOST_RAM_GB`: Host'unuzun toplam RAM'i (GB). Bilgisayar Docker Desktop / WSL2 ise dogru ayarlamak kritik.
- `OLLAMA_MEM_LIMIT`: Ollama container'inin maks bellegi (varsayilan 6g). Host RAM'inizin yarisini gecirmeyin.

### 2. Servisleri baslat
CPU-only (Windows dahil her ortam):
```bash
docker compose up -d --build
```
GPU'lu (NVIDIA Container Toolkit kurulu olmali):
```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

### 3. Ilk pull ve gozlem
Yeni varsayilan: **lazy pull**. Sistem aciliyken sadece bir adet kucuk "seed" model indirilir. Diger modeller, ilk gelen istekte (veya panelden manuel `pull` ile) indirilir. Bu sayede ilk acilista bilgisayariniz `1-25 GB model indirme + RAM doldurma` saldirisina ugramaz.

```bash
docker compose logs -f gateway
```
veya tarayicidan `http://localhost:8080/ui/dashboard` (admin/admin ile giris).

### 4. UI'yi ac
- Sohbet ve Panel: http://localhost:8080
- Grafana: http://localhost:3000 (admin / admin)
- Prometheus: http://localhost:9090
- API dokumantasyonu: http://localhost:8080/docs

### 5. Yuk simulasyonu (opsiyonel)
```bash
docker compose --profile sim up simulator
```

---

## Kapasite Profilleri

Sistem `runtime_config['profile']` (varsayilan `auto`) degerine gore farkli stratejiler uygular. Profil donanima bakilarak seciliyor — manuel override icin `.env`'de `CAPACITY_PROFILE` veya panelden "Profil" alani.

| Profil | RAM/VRAM Butce Orani | Max Aktif Model | Max Yuklu Model | Paralel | Kategoriler |
|---|---|---|---|---|---|
| `lite`        | %25 CPU / %55 GPU | 1 | 1 | 1 | fallback |
| `balanced`    | %40 CPU / %70 GPU | 3 | 1 | 1 | fallback, text, code |
| `performance` | %55 CPU / %80 GPU | 6 | 2 | 2 | fallback, text, code, reasoning |

**Otomatik secim:**
- < 6 GB RAM (veya VRAM <2 GB) → `lite`
- 6-16 GB RAM → `balanced`
- > 12 GB VRAM → `performance`

Profil her kategoriden **en kucuk** modeli secer. Boyle olunca model katalogundaki agir 7B modeller pasif kalir, sistem swap'a inmez.

---

## Demo Hesaplari

| Kullanici      | Sifre   | Departman   | Rol   |
|----------------|---------|-------------|-------|
| admin          | admin   | engineering | admin |
| hr_user        | hr123   | hr          | user  |
| dev_user       | dev123  | engineering | user  |
| legal_user     | legal123| legal       | user  |
| finance_user   | fin123  | finance     | user  |
| marketing_user | mkt123  | marketing   | user  |
| guest          | guest   | general     | user  |

> Uretim ortaminda `config/default_users.yaml` dosyasini silin veya tum sifreleri degistirin.

---

## Modeller (Mayis 2026 katalogu)

`config/model_catalog.yaml` icinde 11 hafif model tanimli (0.5B ile 7B arasi). Aktif/pasif ayrimi profil + donanim profilinizden otomatik yapilir. Yonetim panelinden manuel olarak da listeyi sabitleyebilirsiniz.

---

## Yonlendirme (Routing) Kurallari

`model_catalog.yaml` icindeki `routing_rules` bolumunden duzenlenebilir. Varsayilan kurallar:

1. Prompt'ta kod blogu (\`\`\` veya `def `, `function `, `class `, `SELECT`, `=>`) varsa **code**.
2. Prompt'ta `hesapla`, `formul`, `matematik`, `denklem` varsa **reasoning**.
3. Aksi halde kullanicinin departmaninin `primary_category` degeri.
4. Hedef kategoride hazir model yoksa **fallback**.

Yonetici hesabi tek bir istek icin spesifik model secebilir (UI: Sohbet sayfasi).

---

## API Yuzeyi (ozet)

| Yontem | Yol | Aciklama |
|---|---|---|
| POST | `/login` | Kullanici/sifre → JWT |
| POST | `/api/v1/chat` | Yetkili istek → otomatik secilmis modele yonlendir |
| GET  | `/api/v1/models` | Aktif/pasif modeller ve canli durumlari |
| POST | `/api/v1/system/pull/{model_id}` | Manuel pull tetikle (admin) |
| GET  | `/api/v1/system/profile` | Donanim + kapasite + runtime config |
| GET  | `/api/v1/system/profiles` | Tum profil tanimlari |
| GET  | `/api/v1/system/config` | Mevcut runtime config |
| PUT  | `/api/v1/system/config` | Runtime config guncelle (admin) |
| POST | `/api/v1/system/replan` | Manuel yeniden plan (admin) |
| GET  | `/api/v1/usage/me` | Kullanicinin kullanim ozeti |
| GET  | `/api/v1/usage/global` | Tum kullanim (admin) |
| GET  | `/api/v1/audit` | Audit log (admin) |
| GET  | `/api/v1/users` | Kullanici listesi (admin) |
| GET  | `/metrics` | Prometheus formatinda metrikler |
| GET  | `/healthz`, `/readyz` | Saglik kontrolu |

OpenAPI/Swagger dokumantasyonu `/docs` yolundan ulasilabilir.

---

## Izleme (Grafana)

Hazir dashboard `monitoring/grafana/dashboards/overview.json` icindedir. Panelleri:

- Aktif istekler, aktif model sayisi, yuklu model sayisi
- Fallback ve rate-limit oranlari
- Token uretim hizi
- Departman bazinda istek hizi
- Model bazinda p95 gecikme
- Model kullanim dagilimi (pie)
- Hata orani

---

## Sorun Giderme

| Belirti | Cozum |
|---|---|
| Bilgisayar acilista kilitleniyor | `.env` icinde `CAPACITY_PROFILE=lite` ve `OLLAMA_MEM_LIMIT=3g` yapip yeniden baslatin. |
| `ollama` saglikli olmuyor | Ilk acilis Docker imajini indirir, 1-2 dakika bekleyin. `docker compose logs ollama` |
| Modeller cok yavas iniyor | Ilk pull ag bant genisligine bagli. Loglardan ilerlemeyi izleyin. |
| Gateway 502 donuyor | Ollama hazir degil ya da model pull bitmemis olabilir. `/readyz` 503 donerse normaldir. |
| GPU goremiyor | `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up` kullanin; NVIDIA Container Toolkit kurulu olmali. |
| `JWT_SECRET zorunlu` hatasi | `.env` dosyasini olusturup `JWT_SECRET` doldurun. |
| Yetersiz RAM uyarisi | Profili `lite`'a alin veya `HOST_RAM_GB` degerini gercek RAM'iniz olarak set edin. |
| Yanlis RAM tespiti (Docker Desktop) | `.env` icinde `HOST_RAM_GB=16` gibi acikca yazin. |

---

## Gelistirme

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r app/requirements.txt -r simulator/requirements.txt pytest

# Birim testleri
pytest -q tests/
```

Yapi `app/` (Python paketi), `config/` (model katalogu, kullanici tohumu), `monitoring/` (Prom/Grafana), `simulator/` (yuk ureteci) klasorlerinden olusur.

---

## Lisans

MIT — bitirme projesi kapsaminda serbestce kullanilabilir.
