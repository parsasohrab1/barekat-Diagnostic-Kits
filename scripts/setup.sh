#!/usr/bin/env bash
set -euo pipefail

echo "==> Setting up barekat-Diagnostic-Kits..."

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

echo "==> Installing Python dependencies..."
pip install -e ".[dev]"

echo "==> Starting infrastructure..."
docker compose up -d postgres redis minio

echo "==> Waiting for PostgreSQL..."
for i in $(seq 1 30); do
  if docker compose exec -T postgres pg_isready -U barekat -d barekat_diagnostics > /dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "==> Running database migrations..."
alembic upgrade head

echo "==> Generating synthetic data..."
python scripts/generate_data.py --samples 800

echo "==> Training classifier..."
python scripts/train_model.py

echo ""
echo "Infrastructure ready!"
echo "  API:    http://localhost:8000/docs"
echo "  MinIO:  http://localhost:9001"
echo ""
echo "Run: make api"
