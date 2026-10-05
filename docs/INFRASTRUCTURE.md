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
| PostgreSQL | 5432 | Stores samples and diagnosis results |
| Redis | 6379 | Celery queue and cache |
| MinIO | 9000/9001 | Stores raw curves and calibration files |
| API | 8000 | Diagnosis REST API |
| Worker | — | Asynchronous processing (training, data generation) |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/health` | Service health check |
| POST | `/api/v1/samples/` | Register a sample |
| POST | `/api/v1/samples/upload` | Upload a sample + raw curve |
| GET | `/api/v1/samples/{sample_id}` | Sample details |
| POST | `/api/v1/calibration/` | Record kit calibration |
| POST | `/api/v1/calibration/upload` | Upload standard curve to MinIO |
| POST | `/api/v1/diagnosis/analyze` | Sync analysis (default) |
| POST | `/api/v1/diagnosis/analyze?async_mode=true` | Register an asynchronous job — returns the job ID |
| GET | `/api/v1/diagnosis/jobs/{job_id}` | Job status, progress and result |
| POST | `/api/v1/diagnosis/sync` | Receive a report from an offline device |
| POST | `/api/v1/diagnosis/batch` | Batch processing of samples |
| GET | `/api/v1/diagnosis/reports/{sample_id}/{report_id}/pdf` | Download the report PDF |

### Edge / Offline-First

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/edge/offline/analyze` | Local analysis without the central API |
| GET | `/api/v1/edge/offline/pending` | Number of samples awaiting sync |
| POST | `/api/v1/edge/offline/sync` | Synchronize with the central server |
| POST | `/api/v1/edge/onnx/export` | sklearn → ONNX export |
| POST | `/api/v1/edge/onnx/benchmark` | Latency benchmark (<100ms target) |

### ML / IVD

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/ml/train` | Training + IVD evaluation + registry recording |
| POST | `/api/v1/ml/evaluate` | Sensitivity/Specificity evaluation with CI, ROC-AUC |
| GET | `/api/v1/ml/registry` | Model registry status |
| POST | `/api/v1/ml/registry/ab-test` | Configure A/B test |
| POST | `/api/v1/ml/registry/rollback/{version}` | Automatic rollback |
| POST | `/api/v1/ml/explain` | Feature importance for diagnosis |

## Kit Types

| Kit | Features | Default cutoff |
|-----|---------|----------------|
| qPCR | Ct value, sigmoid curve | 30 cycles |
| ELISA | OD ratio (450/620) | 1.0 |
| Spectroscopy | peak intensity, wavelength bands | 0.5 a.u. |

## Pipeline

```
Raw Sensor Data → Preprocessing → Feature Extraction → QC → ML Classification → Diagnosis Report
```

| Stage | Module | Description |
|-------|--------|-------------|
| Preprocessing | `pipeline/preprocessing.py` | Noise removal, normalization |
| Feature Extraction | `pipeline/feature_extraction.py` | Ct value, slope, AUC |
| Quality Control | `pipeline/qc.py` | Quality check, alerts |
| Classification | `ml/classifier.py` | Random Forest / SVM |
| IVD Evaluation | `ml/evaluation.py` | Sensitivity/Specificity + CI, ROC-AUC, CV |
| Model Registry | `ml/registry.py` | versioning, A/B test, rollback |
| Explainability | `ml/explainability.py` | feature importance |

## Project Structure

```
├── docker-compose.yml       # infrastructure services
├── Dockerfile               # API/Worker image
├── src/barekat_diagnostics/ # main code
│   ├── api/                 # FastAPI endpoints
│   ├── core/                # settings and database
│   ├── data/                # synthetic data generation
│   ├── ml/                  # ML models + ONNX export
│   ├── edge/                # SQLite offline store + sync
│   ├── models/              # ORM models
│   ├── pipeline/            # QC, preprocessing, feature extraction
│   ├── schemas/             # Pydantic schemas
│   └── tasks/               # Celery tasks
├── scripts/                 # helper scripts
├── data/                    # data and models
├── tests/                   # tests
└── alembic/                 # database migrations
```

## Makefile Commands

```bash
make setup          # install dependencies
make infra          # start Docker
make generate-data  # generate realistic data
make evaluate       # IVD evaluation
make train          # train the model (+ auto ONNX export)
make export-onnx    # manual ONNX export for edge
make api            # run the API
make worker         # Celery worker
make migrate        # database migration
make test           # run tests
```

## Edge Deployment

For deployment on bedside devices with a weak CPU:

```bash
pip install -e ".[edge]"
make train              # training + automatic ONNX export
make export-onnx        # manual export + benchmark
python scripts/offline_cli.py analyze --sample-id LAB-001 --ct-value 22.5
python scripts/offline_cli.py sync --api http://localhost:8000/api/v1
```

**Inference path:** `sklearn → ONNX (skl2onnx) → onnxruntime` — target under 100ms on CPU.

**Offline-First:** local SQLite (`data/offline/local.db`) + pending queue + embedded model with no API needed.

**Async jobs:** `POST /diagnosis/analyze?async_mode=true` → Celery worker → `GET /diagnosis/jobs/{id}`

| Env | Default | Description |
|-----|---------|-------------|
| `INFERENCE_BACKEND` | `sklearn` | `onnx` for edge |
| `ONNX_MODEL_PATH` | `data/models/diagnostic_classifier_v1.onnx` | ONNX model path |
| `OFFLINE_SQLITE_PATH` | `data/offline/local.db` | Local database |
| `OFFLINE_SYNC_API_URL` | `http://localhost:8000/api/v1` | Sync destination |

## Quality Control Thresholds

| Parameter | Default | Description |
|-----------|---------|-------------|
| `QC_MIN_QUALITY_SCORE` | 0.5 | Minimum quality score |
| `QC_MIN_SIGNAL_TO_NOISE` | 1.2 | Minimum signal-to-noise ratio |
| `QC_MIN_AMPLIFICATION_EFFICIENCY` | 0.8 | Minimum amplification efficiency |
