"""Tests for the API surface."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint_reports_backend_running() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "backend"}


def test_routes_are_mounted_under_the_configured_prefix() -> None:
    assert app.url_path_for("health_check") == "/api/health"
