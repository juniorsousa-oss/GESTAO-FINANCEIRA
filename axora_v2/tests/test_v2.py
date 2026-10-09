import os
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from axora_v2.metrics import compute
from axora_v2.security import hash_password, matches
from axora_v2.main import app, sanitize


def test_hashes_are_compatible():
    encoded = hash_password("senha-unica-com-12-ou-mais")
    assert matches("senha-unica-com-12-ou-mais", encoded)
    assert not matches("errada", encoded)
    assert encoded.startswith("pbkdf2_sha256$390000$")


def test_financial_totals_and_period():
    summary = compute(
        [
            {"value": 1200, "classification": "ENTRADA", "competence": "10/2026"},
            {"value": 300, "classification": "SAÍDA", "competence": "10/2026", "category": "MERCADO"},
        ],
        [{"type": "Saída", "status": "Não pago", "final_value": 125},
         {"type": "Entrada", "status": "Não pago", "final_value": 200},
         {"type": "Saída", "status": "Pago", "final_value": 500}],
        [{"balance": 900}], [{"open_value": 450}],
        {"net_income": 3000, "investment_pct": 20, "fixed_pct": 50, "leisure_pct": 30, "emergency_months": 6},
    )
    assert summary["realized"] == 900
    assert summary["located"] == 900
    assert summary["to_receive"] == 200
    assert summary["to_pay"] == 125
    assert summary["projected"] == 975
    assert summary["debt_open"] == 450
    assert summary["goals"]["emergency"] == 18000
    assert summary["categories"] == [{"name": "MERCADO", "value": 300}]


def test_financial_validation():
    result = sanitize("forecasts", {
        "description": "Aluguel", "value": 1000, "adjustment": -10, "type": "Saída",
        "status": "Não pago", "competence": "10/2026"
    }, creating=True)
    assert result["adjustment"] == -10
    for invalid in [
        {"description": "", "value": 10, "classification": "ENTRADA"},
        {"description": "Teste", "value": -1, "classification": "SAÍDA"},
        {"description": "Teste", "value": 10, "classification": "OUTRO"},
        {"description": "Teste", "value": 10, "classification": "ENTRADA", "competence": "13/2026"},
    ]:
        with pytest.raises(HTTPException):
            sanitize("movements", invalid, creating=True)
    with pytest.raises(HTTPException):
        sanitize("movements", {"id": 1, "value": 20})


def test_sessions_require_login(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-not-a-real-token")
    monkeypatch.setenv("SESSION_SECRET", "a"*50)
    with TestClient(app) as client:
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["engine"] == "FastAPI"
        assert client.get("/api/snapshot").status_code == 401
        assert client.get("/api/export").status_code == 401
        assert client.get("/").status_code == 200
        assert b"AXORA" in client.get("/").content


def test_invalid_secret_fails_startup(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test")
    monkeypatch.setenv("SESSION_SECRET", "short")
    with pytest.raises(RuntimeError):
        with TestClient(app):
            pass
