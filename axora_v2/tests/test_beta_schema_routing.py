"""Seleção segura do schema PostgREST: evita escrita/leitura BETA em public."""
import pytest
from fastapi import HTTPException
from axora_v2 import db


@pytest.mark.parametrize("verb,header",[
    ("GET","Accept-Profile"),("HEAD","Accept-Profile"),("POST","Content-Profile"),
    ("PATCH","Content-Profile"),("DELETE","Content-Profile")
])
def test_beta_header_never_selects_production(monkeypatch,verb,header):
    monkeypatch.setenv("SUPABASE_DB_SCHEMA","axora_beta")
    monkeypatch.setenv("SUPABASE_KEY","only-test-key")
    actual=db.headers(method=verb)
    assert actual[header]=="axora_beta"
    other="Accept-Profile" if header=="Content-Profile" else "Content-Profile"
    assert other not in actual


def test_production_default_stays_unchanged(monkeypatch):
    monkeypatch.delenv("SUPABASE_DB_SCHEMA",raising=False)
    assert db.selected_schema()=="public"
    assert db.headers()["Accept-Profile"]=="public"


def test_unknown_schema_cannot_fall_back_to_production(monkeypatch):
    monkeypatch.setenv("SUPABASE_DB_SCHEMA","invalid; public")
    with pytest.raises(HTTPException) as e:
        db.headers()
    assert e.value.status_code==503
