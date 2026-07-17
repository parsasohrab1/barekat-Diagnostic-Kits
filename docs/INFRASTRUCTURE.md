# Infrastructure

## Architecture

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
                    │
                    ▼
         Pipeline: QC → Feature Extraction → Classification
```

## Quick Start

```bash
cp .env.example .env
docker compose up -d
pip install -e ".[dev]"
alembic upgrade head
python scripts/generate_data.py --samples 800
python scripts/train_model.py
uvicorn barekat_diagnostics.api.main:app --reload
```

- API Docs: http://localhost:8000/docs
- MinIO Console: http://localhost:9001

## Services

| Service | Port | Role |
|---------|------|------|
| PostgreSQL | 5432 | ذخیره نمونه‌ها و نتایج تشخیص |
| Redis | 6379 | صف Celery و کش |
| MinIO | 9000/9001 | ذخیره منحنی‌های خام و فایل‌های کالیبراسیون |
| API | 8000 | REST API تشخیص |
| Worker | — | پردازش ناهمزمان (آموزش، تولید داده) |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/health` | بررسی سلامت سرویس‌ها |
| POST | `/api/v1/samples/` | ثبت نمونه |
| POST | `/api/v1/samples/upload` | آپلود نمونه + منحنی خام |
| GET | `/api/v1/samples/{sample_id}` | جزئیات نمونه |
| POST | `/api/v1/calibration/` | ثبت کالیبراسیون کیت |
| POST | `/api/v1/calibration/upload` | آپلود standard curve به MinIO |
| POST | `/api/v1/diagnosis/analyze` | تحلیل sync (پیش‌فرض) |
| POST | `/api/v1/diagnosis/analyze?async_mode=true` | ثبت job ناهمزمان — برگرداندن job ID |
| GET | `/api/v1/diagnosis/jobs/{job_id}` | وضعیت، progress و نتیجه job |
| POST | `/api/v1/diagnosis/sync` | دریافت گزارش از دستگاه offline |
| POST | `/api/v1/diagnosis/batch` | پردازش batch نمونه‌ها |
| GET | `/api/v1/diagnosis/reports/{sample_id}/{report_id}/pdf` | دانلود PDF گزارش |

### Edge / Offline-First

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/edge/offline/analyze` | تحلیل محلی بدون API مرکزی |
| GET | `/api/v1/edge/offline/pending` | تعداد نمونه‌های در انتظار sync |
| POST | `/api/v1/edge/offline/sync` | همگام‌سازی با سرور مرکزی |
| POST | `/api/v1/edge/onnx/export` | sklearn → ONNX export |
| POST | `/api/v1/edge/onnx/benchmark` | benchmark latency (<100ms هدف) |

### ML / IVD

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/ml/train` | آموزش + ارزیابی IVD + ثبت registry |
| POST | `/api/v1/ml/evaluate` | ارزیابی Sensitivity/Specificity با CI، ROC-AUC |
| GET | `/api/v1/ml/registry` | وضعیت model registry |
| POST | `/api/v1/ml/registry/ab-test` | تنظیم A/B test |
| POST | `/api/v1/ml/registry/rollback/{version}` | rollback خودکار |
| POST | `/api/v1/ml/explain` | feature importance برای تشخیص |

## Kit Types

| Kit | ویژگی‌ها | Cutoff پیش‌فرض |
|-----|---------|----------------|
| qPCR | Ct value، منحنی sigmoid | 30 cycles |
| ELISA | OD ratio (450/620) | 1.0 |
| Spectroscopy | peak intensity، wavelength bands | 0.5 a.u. |

## Pipeline

```
Raw Sensor Data → Preprocessing → Feature Extraction → QC → ML Classification → Diagnosis Report
```

| Stage | Module | Description |
|-------|--------|-------------|
| Preprocessing | `pipeline/preprocessing.py` | حذف نویز، نرمال‌سازی |
| Feature Extraction | `pipeline/feature_extraction.py` | Ct value، شیب، AUC |
| Quality Control | `pipeline/qc.py` | بررسی کیفیت، هشدار |
| Classification | `ml/classifier.py` | Random Forest / SVM |
| IVD Evaluation | `ml/evaluation.py` | Sensitivity/Specificity + CI، ROC-AUC، CV |
| Model Registry | `ml/registry.py` | versioning، A/B test، rollback |
| Explainability | `ml/explainability.py` | feature importance |

## Project Structure

```
├── docker-compose.yml       # سرویس‌های زیرساخت
├── Dockerfile               # ایمیج API/Worker
├── src/barekat_diagnostics/ # کد اصلی
│   ├── api/                 # FastAPI endpoints
│   ├── core/                # تنظیمات و پایگاه داده
│   ├── data/                # تولید داده سنتتیک
│   ├── ml/                  # مدل‌های ML + ONNX export
│   ├── edge/                # SQLite offline store + sync
│   ├── models/              # ORM models
│   ├── pipeline/            # QC، پیش‌پردازش، استخراج ویژگی
│   ├── schemas/             # Pydantic schemas
│   └── tasks/               # Celery tasks
├── scripts/                 # اسکریپت‌های کمکی
├── data/                    # داده و مدل‌ها
├── tests/                   # تست‌ها
└── alembic/                 # مهاجرت‌های پایگاه داده
```

## Makefile Commands

```bash
make setup          # نصب وابستگی‌ها
make infra          # راه‌اندازی Docker
make generate-data  # تولید داده realistic
make evaluate       # ارزیابی IVD
make train          # آموزش مدل (+ auto ONNX export)
make export-onnx    # export دستی ONNX برای edge
make api            # اجرای API
make worker         # Celery worker
make migrate        # مهاجرت پایگاه داده
make test           # اجرای تست‌ها
```

## Edge Deployment

برای استقرار روی دستگاه‌های bedside با CPU ضعیف:

```bash
pip install -e ".[edge]"
make train              # آموزش + export خودکار ONNX
make export-onnx        # export دستی + benchmark
python scripts/offline_cli.py analyze --sample-id LAB-001 --ct-value 22.5
python scripts/offline_cli.py sync --api http://localhost:8000/api/v1
```

**مسیر inference:** `sklearn → ONNX (skl2onnx) → onnxruntime` — هدف زیر ۱۰۰ms روی CPU.

**Offline-First:** SQLite محلی (`data/offline/local.db`) + صف pending + مدل embedded بدون نیاز به API.

**Async jobs:** `POST /diagnosis/analyze?async_mode=true` → Celery worker → `GET /diagnosis/jobs/{id}`

| Env | Default | Description |
|-----|---------|-------------|
| `INFERENCE_BACKEND` | `sklearn` | `onnx` برای edge |
| `ONNX_MODEL_PATH` | `data/models/diagnostic_classifier_v1.onnx` | مسیر مدل ONNX |
| `OFFLINE_SQLITE_PATH` | `data/offline/local.db` | پایگاه محلی |
| `OFFLINE_SYNC_API_URL` | `http://localhost:8000/api/v1` | مقصد sync |

## Quality Control Thresholds

| Parameter | Default | Description |
|-----------|---------|-------------|
| `QC_MIN_QUALITY_SCORE` | 0.5 | حداقل امتیاز کیفیت |
| `QC_MIN_SIGNAL_TO_NOISE` | 1.2 | حداقل نسبت سیگنال به نویز |
| `QC_MIN_AMPLIFICATION_EFFICIENCY` | 0.8 | حداقل بازدهی تکثیر |
