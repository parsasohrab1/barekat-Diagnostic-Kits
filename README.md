# barekat-Diagnostic-Kits

هدف: توسعه یک نرم‌افزار هوشمند برای تحلیل داده‌های خام کیت‌های تشخیصی (مانند داده‌های qPCR، توالی‌یابی یا طیف‌سنجی) برای تشخیص دقیق و سریع بیماری.

## معماری زیرساخت

```
┌──────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Lab Device /    │────▶│  FastAPI     │────▶│  PostgreSQL     │
│  Sensor Input    │     │  REST API    │     │  (Samples)      │
└──────────────────┘     └──────┬───────┘     └─────────────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
             ┌──────────┐  ┌──────────┐  ┌─────────────┐
             │  Celery  │  │  MinIO   │  │  ML Model   │
             │  Worker  │  │  (S3)    │  │  (sklearn)  │
             └──────────┘  └──────────┘  └─────────────┘
```

### سرویس‌ها

| سرویس | پورت | نقش |
|--------|------|-----|
| PostgreSQL | 5432 | ذخیره نمونه‌ها و نتایج تشخیص |
| Redis | 6379 | صف Celery |
| MinIO | 9000/9001 | ذخیره منحنی‌های خام |
| API | 8000 | REST API تشخیص |

## ورودی‌ها

داده‌های خام حسگرها، اطلاعات مربوط به کالیبراسیون کیت، و شناسه بیمار.

## پردازش

پیش‌پردازش (حذف نویز، نرمال‌سازی)، استخراج ویژگی‌های کلیدی (مانند Ct value در qPCR)، و استفاده از یک مدل طبقه‌بندی آموزش‌دیده (مانند SVM، Random Forest یا شبکه عصبی) برای تصمیم‌گیری نهایی (مثبت/منفی).

## خروجی‌ها

گزارش تشخیص، سطح اطمینان مدل، و هشدار در صورت وجود داده‌های غیرقابل اعتماد (کنترل کیفیت خودکار).

## محدودیت‌های کلیدی

دقت و ویژگی (Sensitivity/Specificity) بالا، زمان پردازش کوتاه برای استفاده بالینی، توانایی کار بر روی دستگاه‌های با توان پردازشی محدود، و مقاوم بودن در برابر نویز و تغییرات آزمایشگاهی.

## راه‌اندازی سریع

```bash
cp .env.example .env
pip install -e ".[dev]"
docker compose up -d
alembic upgrade head
python scripts/generate_data.py --samples 800
python scripts/train_model.py
uvicorn barekat_diagnostics.api.main:app --reload
```

یا با Makefile:

```bash
make setup
make infra
make migrate
make generate-data
make train
make api
```

مستندات زیرساخت: [docs/INFRASTRUCTURE.md](docs/INFRASTRUCTURE.md)

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/health` | بررسی سلامت |
| POST | `/api/v1/import/qpcr` | واردسازی CSV/RDML دستگاه qPCR |
| POST | `/api/v1/batches/` | ایجاد بچ آزمایشگاهی |
| POST | `/api/v1/batches/{id}/controls` | ثبت کنترل مثبت/منفی |
| POST | `/api/v1/batches/{id}/validate` | اعتبارسنجی اجباری کنترل‌ها |
| POST | `/api/v1/diagnosis/analyze` | تحلیل نمونه |
| GET | `/api/v1/diagnosis/jobs` | لیست Jobها |
| POST | `/api/v1/diagnosis/reports/{id}/approve` | تأیید نتیجه توسط کاربر |
| GET | `/api/v1/audit/` | لاگ حسابرسی |
| GET | `/api/v1/dashboard/summary` | خلاصه داشبورد اپراتور |
| POST | `/api/v1/ml/evaluate-pilot` | Se/Sp + CI روی دادهٔ پایلوت |
| GET | `/dashboard` | UI اپراتور آزمایشگاه |

## فاز ۳ — Edge / ناوگان / چندمرکزی

- بسته کیوسک ONNX قفل‌شده: `python scripts/build_edge_bundle.py --version v1`
- Sync مقاوم (retry/backoff + conflict): `POST /edge/offline/sync`
- ناوگان مدل: `/api/v1/fleet/releases` · `/manifest/{device_id}` · `scripts/fleet_update_device.py`
- Multi-tenant: `/api/v1/tenants/` · `/centers/{id}/aggregate`
- Latency SLA روی CPU ضعیف: `EDGE_LATENCY_SLA_MS=100` + ORT single-thread

```bash
alembic upgrade head
pip install -e ".[edge]"
```

## فاز ۴ — پشتیبانی تصمیم پیشرفته

- پنل چندبیماری/مارکر: `POST /api/v1/panels/` · `POST /api/v1/panels/analyze` (پیش‌فرض `RESP-V1`)
- توضیح‌پذیری بالینی برای پزشک/بایولوژیست در گزارش تشخیص (`clinical_explanation`)
- پرونده چندکیتی (qPCR + ELISA): `POST /api/v1/cases/` · `/assays` · `/fuse`
- پیشنهاد reassessment روی QC مشکوک: `GET /api/v1/reassessments/` · `POST .../accept`
- یادگیری نظارت‌شده (HITL): `POST /api/v1/hitl/feedback` · `/export` · `/retrain`

```bash
alembic upgrade head   # شامل migration 007
pytest tests/test_phase4_advanced_dss.py -q
```


## ساختار پروژه

```
├── src/barekat_diagnostics/   # کد اصلی
│   ├── api/                     # FastAPI
│   ├── pipeline/                # QC، پیش‌پردازش، استخراج ویژگی
│   ├── ml/                      # مدل‌های ML
│   └── data/                    # تولید داده سنتتیک
├── scripts/                     # اسکریپت‌های کمکی
├── data/                        # داده و مدل‌ها
├── tests/                       # تست‌ها
└── docker-compose.yml           # زیرساخت Docker
```

## فرمول تولید داده‌های سنتتیک

تولید داده برای کیت‌های تشخیص شامل شبیه‌سازی سیگنال‌های خام و نتایج نهایی است.

### فرمول پیشنهادی برای داده‌های qPCR

1. **مدل‌سازی سیگنال پایه**: برای هر نمونه، یک منحنی رشد نمایی (Sigmoid) با پارامترهای مختلف (شیب، نقطه عطف) تولید می‌شود.
2. **افزودن نویز و خطا**: نویز پس‌زمینه (گوسی)، نوسانات فاز نمایی، و خطاهای سیستماتیک کالیبراسیون.
3. **تولید داده‌های بالینی**: به هر نمونه وضعیت واقعی (مثبت/منفی) اختصاص داده می‌شود.
4. **تولید مجموعه داده نهایی**: پایگاه داده ویژگی‌های استخراج‌شده (Ct value) با برچسب واقعی.

```bash
python scripts/generate_data.py --samples 800
```
