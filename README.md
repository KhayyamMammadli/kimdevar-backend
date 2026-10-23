# KimdəVar — Python FastAPI

Mobil pilot üçün SQLite-də saxlanan sorğular, mağazalar, təkliflər və yazışmalar. Production servisi deyil. Real SMS və AI hələ inteqrasiya olunmayıb.

## Codespaces-də işə sal

**Code → Codespaces → Create codespace on main**. Quraşdırma bitdikdən sonra:

```bash
DEMO_MODE=true python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Dependency-lər quraşdırılmayıbsa əvvəl `pip install -r requirements.txt` et.

**Ports** bölməsində 8000 görünəcək. **Open in Browser** ilə aç, URL sonuna `/docs` əlavə et: interaktiv API sənədi. Sağlamlıq: `/health`.

Telefonun API-yə daxil olması üçün 8000 portunun **Port Visibility → Public** seçimi lazım ola bilər. Bu, demo API-ni internetdən əlçatan edir; bu rejimdə real şəxsi məlumat yazma. Demo giriş hər kəsə ortaq alıcı/satıcı/admin hesabını verir. Production auth hazır olmadan bu servisi müştərilərə vermə. Default `DEMO_MODE=false`-dur.

Mobil tətbiqin **Bağlantı** ekranında portun Forwarded Address ünvanını saxla (məsələn `https://NAME-8000.app.github.dev`). `/docs` hissəsini əlavə etmə. Sonra alıcı və ya satıcı demo hesabı ilə daxil ol. Native fetch üçün CORS tələb olunmur; web preview üçün öz ünvanını `CORS_ORIGINS` siyahısına əlavə et.

## Lokal

Python 3.12 tövsiyə olunur (minimum 3.10).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
DEMO_MODE=true python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

`.env.example` sənəddir; tətbiq .env faylını avtomatik oxumur. Dəyərləri shell-də export et. Codespaces stop ediləndə server əlçatan olmur. `data/` içindəki baza və şəkillər restartda qalır; Codespace silinəndə itir. Serverless və efemer diskli production hosta bu storage ilə deploy etmə.

## API

- `POST /auth/demo` — `{ "role": "buyer" | "seller" | "admin" }` (yalnız DEMO_MODE=true).
- `GET/PATCH/DELETE /me`, `POST /auth/logout`.
- `POST /ai/analyze` — qayda əsaslı demo; provider açıq göstərilir, təsdiq tələb edir.
- `POST /uploads`, `GET /uploads/{id}` — 5 MB limit; şəkil decode, resize, JPEG re-encode; giriş yoxlaması.
- `GET/POST /requests`, `GET/PATCH /requests/{id}`.
- `GET/POST /requests/{id}/offers`, `GET /offers/mine`, `DELETE /offers/{id}`.
- `GET /stores`, `GET/PATCH /stores/mine`, `GET /stores/{id}`.
- `GET /favorites`, `POST/DELETE /favorites/{store_id}`.
- `GET/POST /conversations`, `GET/POST /conversations/{id}/messages`.
- `GET /notifications`, `POST /notifications/read`, `POST /reports`.
- `GET /analytics`, `GET /admin/overview`, `POST /admin/stores/{id}/verify`.

API bearer token-i login cavabından al. Token serverdə yalnız SHA-256 hash kimi saxlanır, 24 saat qüvvədədir. Şəxsi məlumatlar və yazışmalar üçün rol/obyekt giriş yoxlaması var. Alıcı yalnız öz sorğusunu idarə edir; mağaza yalnız uyğun kateqoriya/rayon üzrə sorğuları görür. Mağaza ad/ünvanını dəyişərsə təsdiqi sıfırlanır. Stok və qiymət satıcıdan gəlir, AI onları uydurmur. Bir mağaza/sorğu cütünə bir təklif var; yenidən göndərmə təklifi yeniləyir. Bitmiş təkliflər alıcı siyahısından çıxır.

## Testlər

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Testlər ayrıca müvəqqəti bazada işləyir: tam sorğu–təklif–mesaj axını, sessiya ləğvi, aidiyyətsiz istifadəçinin girişi, şəkil doğrulaması və mağaza təsdiqi.

## Növbəti production mərhələsi

- SMS/OTP və real mağaza qeydiyyatı, rate limiting və abuse nəzarəti.
- Supabase/Postgres miqrasiyası, Storage və backup siyasəti.
- Real multimodal AI provayderi; qiymət limiti və qeyri-müəyyənlik idarəsi.
- Push, xəritə/məsafə, real-time chat, daha geniş moderasiya.
- Məxfilik sənədləri, məlumat saxlama müddəti və mağaza buraxılışı.

Supabase və Render hesablarında bu dəyişiklik zamanı heç bir resurs yaradılmayıb və dəyişdirilməyib. API açarları repoya yazılmır.

Mobil repo: https://github.com/KhayyamMammadli/kimdevar-mobile
