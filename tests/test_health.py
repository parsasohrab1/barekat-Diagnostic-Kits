"""Tests for API health endpoints."""

from fastapi.testclient import TestClient

from barekat_diagnostics.api.main import create_app


def test_liveness():
  client = TestClient(create_app())
  response = client.get("/api/v1/health/live")
  assert response.status_code == 200
  assert response.json()["status"] == "alive"
