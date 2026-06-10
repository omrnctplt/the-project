# Guvenlik ve KVKK Uyumu

Inference Hub, kurum ici (on-premise) calisan bir LLM gateway'idir. Bu belge
alinan guvenlik tedbirlerini ve 6698 sayili KVKK kapsamindaki uyum onlemlerini ozetler.

## Veri envanteri

| Veri | Nerede | Icerik | Saklama |
|---|---|---|---|
| Kullanici hesabi | `data/users.db` | kullanici adi, bcrypt parola ozeti, departman, rol | hesap silinene kadar |
| Denetim kaydi | `data/audit.db` | zaman, kullanici, model, **prompt SHA-256 ozeti + uzunluk** (icerik degil), token sayilari | `RETENTION_DAYS` (varsayilan 180 gun) |
| Kullanim ozeti | `data/usage.db` | gun x kullanici x model istek/token sayilari | `RETENTION_DAYS` |
| Oturum | tarayici localStorage | JWT (max 8 saat) | oturum kapaninca/sure dolunca |

**Saklanmayanlar:** ham prompt/yanit icerigi, IP adresi, konum, cihaz kimligi.
Model yanitlarinin tamami yalnizca kullanici ile model arasinda akar, diske yazilmaz.

## KVKK uyum onlemleri

- **Aydinlatma yukumlulugu (m.10):** `/ui/privacy` sayfasi; giris ekranindan ve
  kenar cubugundan erisilir. Giris formu aydinlatma metnine acik atif icerir.
- **Veri minimizasyonu (m.4):** Prompt icerigi yerine geri donusturulemez SHA-256
  ozeti ve karakter sayisi saklanir.
- **Saklama suresi:** `RETENTION_DAYS` env degiskeni; gunluk arka plan gorevi
  suresi dolan denetim/kullanim kayitlarini otomatik siler (`app/runtime.py: retention_loop`).
- **Silme hakki (m.7, m.11):**
  - `DELETE /api/v1/users/{username}/data` — kisinin tum islem kayitlarini siler (admin).
  - `DELETE /api/v1/users/{username}` — hesabi ve tum verisini siler (admin; admin hesaplari ve
    kendi hesabi korunur). Her iki islem denetim kaydina islenir.
- **Yurt disi aktarim yok:** Sistem tamamen yerel calisir. Canli model kesfi yalnizca
  herkese acik kataloglari (ollama.com, huggingface.co) **indirir**; disari veri gondermez.

## Teknik guvenlik tedbirleri

- **Kimlik dogrulama:** JWT HS256, 8 saat TTL. `JWT_SECRET` verilmezse kriptografik
  olarak guvenli uretilir ve `data/jwt_secret` (0600) dosyasinda saklanir.
- **Parolalar:** bcrypt (cost 10). Yeni parolalar en az 8 karakter.
- **Brute-force korumasi:** `/login` kullanici basina dakikada 10 deneme (429 + Retry-After).
- **Rate limit:** sohbet istekleri departman bazli kayan pencere ile sinirlanir.
- **Yetkilendirme:** rol bazli (user/admin); model yonetimi, denetim kaydi, kullanici
  islemleri ve konfigurasyonn degisikligi yalnizca admin.
- **HTTP basliklari:** CSP, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer` tum yanitlarda.
- **Girdi dogrulama:** tum istek govdesi Pydantic semalariyla dogrulanir; SQL sorgulari
  parametrik; UI cikti uretimi `escapeHtml` + beyaz-listeli markdown renderer (XSS korumasi).
- **Container:** gateway non-root kullanici ile calisir, bellek/CPU limitleri tanimlidir.

## Uretim icin oneriler

1. `config/default_users.yaml` demo hesaplarini silin veya parolalarini degistirin
   (`ADMIN_PASSWORD` env'i ilk seed'de admin parolasini override eder).
2. Ag erisimini ters proxy + TLS arkasina alin (orn. nginx/traefik; HSTS ekleyin).
3. `RETENTION_DAYS` degerini kurumunuzun saklama politikasina gore ayarlayin.
4. `data/` klasorunu yedekleme ve disk sifreleme kapsamina alin.
5. Grafana/Prometheus portlarini yalnizca yonetim agina acin.

## Guvenlik acigi bildirimi

Bir guvenlik acigi bulursaniz lutfen repo uzerinden ozel olarak iletisime gecin;
kamuya acik issue acmadan once duzeltme icin makul sure taniyin.
