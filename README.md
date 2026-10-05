# barekat-Diagnostic-Kits

Goal: develop intelligent software for analyzing raw diagnostic kit data (such as qPCR, sequencing or spectroscopy data) for accurate and rapid disease diagnosis.

## Infrastructure Architecture

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

### Services

| Service | Port | Role |
|--------|------|-----|
| PostgreSQL | 5432 | Stores samples and diagnosis results |
| Redis | 6379 | Celery queue |
| MinIO | 9000/9001 | Stores raw curves |
| API | 8000 | Diagnosis REST API |

## Inputs

Raw sensor data, kit calibration information, and patient ID.

## Processing

Preprocessing (noise removal, normalization), extraction of key features (such as the Ct value in qPCR), and use of a trained classification model (such as SVM, Random Forest or a neural network) for the final decision (positive/negative).

## Outputs

Diagnosis report, model confidence level, and an alert if unreliable data is present (automatic quality control).

## Key Constraints

High accuracy and specificity (Sensitivity/Specificity), short processing time for clinical use, ability to run on devices with limited processing power, and robustness against noise and laboratory variations.

## Quick Start

```bash
cp .env.example .env
pip install -e ".[dev]"
docker compose up -d
alembic upgrade head
python scripts/generate_data.py --samples 800
python scripts/train_model.py
uvicorn barekat_diagnostics.api.main:app --reload
```

Or with the Makefile:

```bash
make setup
make infra
make migrate
make generate-data
make train
make api
```

Infrastructure documentation: [docs/INFRASTRUCTURE.md](docs/INFRASTRUCTURE.md)

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/health` | Health check |
| POST | `/api/v1/import/qpcr` | Import CSV/RDML from a qPCR instrument |
| POST | `/api/v1/batches/` | Create a laboratory batch |
| POST | `/api/v1/batches/{id}/controls` | Record positive/negative controls |
| POST | `/api/v1/batches/{id}/validate` | Mandatory validation of controls |
| POST | `/api/v1/diagnosis/analyze` | Sample analysis |
| GET | `/api/v1/diagnosis/jobs` | List jobs |
| POST | `/api/v1/diagnosis/reports/{id}/approve` | Result approval by a user |
| GET | `/api/v1/audit/` | Audit log |
| GET | `/api/v1/dashboard/summary` | Operator dashboard summary |
| POST | `/api/v1/ml/evaluate-pilot` | Se/Sp + CI on pilot data |
| GET | `/dashboard` | Laboratory operator UI |

## Phase 3 — Edge / Fleet / Multi-center

- Locked ONNX kiosk bundle: `python scripts/build_edge_bundle.py --version v1`
- Resilient sync (retry/backoff + conflict): `POST /edge/offline/sync`
- Model fleet: `/api/v1/fleet/releases` · `/manifest/{device_id}` · `scripts/fleet_update_device.py`
- Multi-tenant: `/api/v1/tenants/` · `/centers/{id}/aggregate`
- Latency SLA on a weak CPU: `EDGE_LATENCY_SLA_MS=100` + ORT single-thread

```bash
alembic upgrade head
pip install -e ".[edge]"
```

## Phase 4 — Advanced Decision Support

- Multi-disease/marker panel: `POST /api/v1/panels/` · `POST /api/v1/panels/analyze` (default `RESP-V1`)
- Clinical explainability for the physician/biologist in the diagnosis report (`clinical_explanation`)
- Multi-kit case (qPCR + ELISA): `POST /api/v1/cases/` · `/assays` · `/fuse`
- Reassessment suggestion on suspicious QC: `GET /api/v1/reassessments/` · `POST .../accept`
- Supervised learning (HITL): `POST /api/v1/hitl/feedback` · `/export` · `/retrain`

```bash
alembic upgrade head   # includes migration 007
pytest tests/test_phase4_advanced_dss.py -q
```


## Project Structure

```
├── src/barekat_diagnostics/   # main code
│   ├── api/                     # FastAPI
│   ├── pipeline/                # QC, preprocessing, feature extraction
│   ├── ml/                      # ML models
│   └── data/                    # synthetic data generation
├── scripts/                     # helper scripts
├── data/                        # data and models
├── tests/                       # tests
└── docker-compose.yml           # Docker infrastructure
```

## Synthetic Data Generation Formula

Data generation for diagnostic kits includes simulation of raw signals and final results.

### Suggested Formula for qPCR Data

1. **Baseline signal modeling**: for each sample, an exponential growth curve (Sigmoid) with different parameters (slope, inflection point) is generated.
2. **Adding noise and error**: background noise (Gaussian), exponential phase fluctuations, and systematic calibration errors.
3. **Generating clinical data**: each sample is assigned a true status (positive/negative).
4. **Generating the final dataset**: a database of extracted features (Ct value) with true labels.

```bash
python scripts/generate_data.py --samples 800
```
