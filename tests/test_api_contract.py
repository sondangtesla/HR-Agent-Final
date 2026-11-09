"""API contract details beyond the mentor's tests: auth, problem details, isolation, readiness."""
from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi.testclient import TestClient

from src.api import create_app
from src.contracts import LeaveRequestView
from src.repository import MemoryRepository

ALYA = {"Authorization": "Bearer token-alya"}
BIMA = {"Authorization": "Bearer token-bima"}
ADMIN = {"Authorization": "Bearer token-admin"}


# --- Authentication ---

def test_unauthenticated_requests_get_401_problem(client: TestClient) -> None:
    for headers in ({}, {"Authorization": "Bearer token-salah"}, {"Authorization": "Basic dG9rZW4tYWx5YQ=="}):
        response = client.get("/api/v1/leave-requests/me", headers=headers)
        assert response.status_code == 401
        assert response.headers["content-type"].startswith("application/problem+json")
        assert response.headers["www-authenticate"] == "Bearer"
        assert response.json()["status"] == 401


# --- Problem details never echo input or internals ---

def test_validation_error_does_not_echo_input(client: TestClient) -> None:
    secret = "alya.pribadi@example.com"
    response = client.post("/api/v1/chat", headers=ALYA, json={"message": secret + "x" * 4000})
    assert response.status_code == 422
    assert secret not in response.text
    assert "message" in response.json()["detail"]


def test_unexpected_error_hides_details(repository: MemoryRepository, client: TestClient) -> None:
    def boom(employee_id):
        raise RuntimeError("database password=hunter2 at 10.0.0.5")

    repository.list_leave_requests = boom
    safe_client = TestClient(client.app, raise_server_exceptions=False)
    response = safe_client.get("/api/v1/leave-requests/me", headers=ALYA)
    assert response.status_code == 500
    assert "hunter2" not in response.text and "10.0.0.5" not in response.text
    assert "Referensi insiden" in response.json()["detail"]


# --- Identity binding through every input channel ---

def test_body_cannot_switch_employee(client: TestClient) -> None:
    response = client.post("/api/v1/chat", headers=ALYA, json={"message": "saldo saya", "employee_id": "EMP-002"})
    assert response.status_code == 200
    assert "annual 8 hari" in response.json()["answer"]  # Alya's 8, not Bima's 3


def test_each_token_sees_only_its_own_balance(client: TestClient) -> None:
    bima = client.post("/api/v1/chat", headers=BIMA, json={"message": "saldo saya"}).json()
    assert "annual 3 hari" in bima["answer"]


def test_leave_requests_are_caller_owned_only(repository: MemoryRepository, client: TestClient) -> None:
    for owner, request_id in (("EMP-001", "LR-ALYA"), ("EMP-002", "LR-BIMA")):
        repository.requests.append((owner, LeaveRequestView(
            request_id=request_id, leave_type="annual", start_date=date(2026, 10, 5),
            end_date=date(2026, 10, 5), business_days=1, status="pending_manager_review",
            created_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
        )))
    ids = [r["request_id"] for r in client.get("/api/v1/leave-requests/me", headers=ALYA).json()]
    assert ids == ["LR-ALYA"]


# --- Traces and monitoring ---

def test_admin_may_read_any_trace_and_unknown_trace_is_404(client: TestClient) -> None:
    trace_id = client.post("/api/v1/chat", headers=ALYA, json={"message": "saldo saya"}).json()["trace_id"]
    assert client.get(f"/api/v1/traces/{trace_id}", headers=ADMIN).status_code == 200
    assert client.get("/api/v1/traces/tr-tidak-ada", headers=ALYA).status_code == 404


def test_monitoring_summary_fields_and_alerts_are_admin_only(client: TestClient) -> None:
    client.post("/api/v1/chat", headers=ALYA, json={"message": "Berapa jatah cuti tahunan?"})
    summary = client.get("/api/v1/monitoring/summary", headers=ADMIN).json()
    for field in ("run_count", "error_rate", "p95_latency_ms", "tool_calls"):  # read by app.py
        assert field in summary
    assert summary["run_count"] == 1
    assert client.get("/api/v1/monitoring/alerts", headers=ALYA).status_code == 403
    assert client.get("/api/v1/monitoring/alerts", headers=ADMIN).json() == []  # 1 run < minimum_samples


# --- Health ---

def test_readiness_reports_each_dependency(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}  # no token needed
    response = client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["cache"] == "degraded"  # NullCache: degraded, yet still ready


def test_readiness_fails_when_database_is_down(repository: MemoryRepository, settings, client: TestClient) -> None:
    repository.health = lambda: False
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["checks"]["database"] == "fail"
