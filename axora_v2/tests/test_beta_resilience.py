"""Regressão do AXORA BETA: favicon resiliente e logs financeiros seguros."""
import logging

import pytest
import requests
from fastapi import HTTPException
from fastapi.testclient import TestClient

from axora_v2 import db
from axora_v2.main import app


def test_favicon_uses_official_mark_when_database_unavailable(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key-not-a-secret")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-with-at-least-thirty-two-chars")
    def unavailable(*args, **kwargs):
        raise HTTPException(502, "Falha na comunicação com a base financeira.")
    monkeypatch.setattr(db, "select", unavailable)
    with TestClient(app) as client:
        for preference in ("favicon", "icon"):
            response = client.get("/api/brand-kit/square-icon", params={"prefer": preference})
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("image/svg+xml")
            assert b"<svg" in response.content
            assert b"viewBox=\"0 0 128 128\"" in response.content


def test_supabase_http_failure_logs_status_only(monkeypatch, caplog):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "never-log-this-secret")
    class Rejected:
        status_code = 401
        def raise_for_status(self):
            raise requests.HTTPError("response-may-contain-sensitive-data", response=self)
    monkeypatch.setattr(requests, "request", lambda *args, **kwargs: Rejected())
    with caplog.at_level(logging.WARNING, logger="axora.database"):
        with pytest.raises(HTTPException) as err:
            db.call("GET", "finance_users", params={"limit": 1})
    assert err.value.status_code == 502
    assert "HTTP 401" in caplog.text
    assert "never-log-this-secret" not in caplog.text
    assert "response-may-contain-sensitive-data" not in caplog.text
