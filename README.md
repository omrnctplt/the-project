# On-Premise AI Gateway

Kucuk ekipler icin departman bazli, hafif ve acik kaynak bir yerel LLM yonlendirme katmani. Tek `docker compose up` ile gateway, Ollama, Prometheus ve Grafana ayaga kalkar. Sistem ilk acilista donanimi olcer, kapasiteyi planlar, departman+keyword tabanli akilli yonlendirme yapar ve butun istekleri denetler.

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
|  - Orchestrator (model lifecycle)      |
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
- En az 8 GB RAM, 20 GB disk
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

### 2. Servisleri baslat
CPU-only (Windows dahil her ortam):
```bash
docker compose up -d --build
```
GPU'lu (NVIDIA Container Toolkit kurulu olmali):
```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

### 3. Modeller arka planda iniyor olabilir
Ilk acilista `AUTO_PULL_MODELS=true` ise gateway aktif modelleri Ollama'ya indirir. Hangi modellerin aktif oldugunu gormek icin:
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
`.env` icindeki `SIM_USERS`, `SIM_DURATION_SEC`, `SIM_DEPT_MIX` degerleri ile dilediginiz kadar yuk uretirsiniz; simulator sonuc raporunu logda basar.

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

## Modeller (Mayis 2026 kataloğu)

`config/model_catalog.yaml` icinde 11 hafif model tanimli:

| Model | Boyut | Kategori | Notlar |
|---|---|---|---|
| llama3.2:1b | 1.2B | text | Hizli metin |
| llama3.2:3b | 3.2B | text | Dengeli metin |
| qwen2.5:1.5b | 1.5B | text | Cok dilli, Turkce iyi |
| qwen2.5:3b | 3.0B | text | Genel amacli |
| gemma2:2b | 2.6B | text | Google Gemma 2 |
| qwen2.5-coder:1.5b | 1.5B | code | Hizli kod tamamlama |
| qwen2.5-coder:3b | 3.1B | code | Orta seviye coding |
| qwen2.5-coder:7b | 7.6B | code | Tam coding asistani |
| deepseek-r1:1.5b | 1.5B | reasoning | Reasoning hafif |
| deepseek-r1:7b | 7.0B | reasoning | Reasoning buyuk |
| qwen2.5:0.5b | 0.5B | fallback | Cok hafif yedek |

Aktif/pasif ayrimi, donanim profilinizden otomatik yapilir. Yonetim panelinden manuel olarak da listeyi sabitleyebilirsiniz.

---

## Yonlendirme (Routing) Kurallari

`model_catalog.yaml` icindeki `routing_rules` bolumunden duzenlenebilir. Varsayilan kurallar:

1. Prompt'ta kod blogu (\`\`\` veya `def `, `function `, `class `, `SELECT`, `=>`) varsa **code** kategorisi.
2. Prompt'ta `hesapla`, `formul`, `matematik`, `denklem` gibi anahtar kelimeler varsa **reasoning**.
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
| GET  | `/api/v1/system/profile` | Donanim + kapasite + runtime config |
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

Hazir dashboard `monitoring/grafana/dashboards/overview.json` icindedir; provisioning sayesinde Grafana acildiginda otomatik yuklenir. Panelleri:

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
| `ollama` saglikli olmuyor | Ilk acilis Docker imajini indirir, 1-2 dakika bekleyin. `docker compose logs ollama` |
| Modeller cok yavas iniyor | Ilk pull ag bant genisligine bagli. Loglardan ilerlemeyi izleyin. |
| Gateway 502 donuyor | Ollama hazir degil ya da model pull bitmemis olabilir. `/readyz` 503 donerse normaldir. |
| GPU goremiyor | `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up` kullanin; NVIDIA Container Toolkit kurulu olmali. |
| `JWT_SECRET zorunlu` hatasi | `.env` dosyasini olusturup `JWT_SECRET` doldurun. |
| Yetersiz RAM uyarisi | `config/model_catalog.yaml` icinden buyuk modelleri kaldirin veya `idle_unload_minutes`'i dusurun. |

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
