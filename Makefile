.PHONY: setup infra generate-data train api worker test lint

setup:
	pip install -e ".[dev]"

infra:
	docker compose up -d postgres redis minio

generate-data:
	python scripts/generate_data.py --samples 800

evaluate:
	python scripts/evaluate_model.py

train:
	python scripts/train_model.py

export-onnx:
	python scripts/export_onnx.py

api:
	uvicorn barekat_diagnostics.api.main:app --reload --host 0.0.0.0 --port 8000

worker:
	celery -A barekat_diagnostics.tasks.celery_app worker --loglevel=info

migrate:
	alembic upgrade head

test:
	pytest tests/ -v

lint:
	ruff check src tests scripts
