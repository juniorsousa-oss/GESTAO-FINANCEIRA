"""Valores recorrentes variáveis: referência opcional, propagação e proteção."""
from pathlib import Path

import pytest
from fastapi import HTTPException
from axora_v2 import provisions

ROOT=Path(__file__).resolve().parents[1]
MIGRATION=ROOT/"migrations/20261023_variable_reference_forecast.sql"


def base(**patch):
    return {
        "description":"Cemig", "category":"Moradia", "responsible":"Titular",
        "start_due_date":"2026-10-23", "planned_value":None,
        "value_mode":"variable", "recurrence":"unlimited", "frequency":"monthly",
        **patch,
    }


def edit(**patch):
    return {
        "scope":"future", "due_date":"2026-10-23",
        "description":"Cemig", "category":"Moradia", "responsible":"Titular",
        "planned_value":None, "value_mode":"variable", **patch,
    }


def test_variable_can_start_without_amount_or_have_initial_estimate():
    assert provisions.clean_provision(base())["p_planned_value"] is None
    assert provisions.clean_provision(base(planned_value=""))["p_planned_value"] is None
    assert provisions.clean_provision(base(planned_value="105.88"))["p_planned_value"]==105.88
    assert provisions.clean_provision(base(value_mode="fixed",planned_value="115.00"))["p_planned_value"]==115
    assert provisions.clean_edit_provision(edit())["p_planned_value"] is None
    assert provisions.clean_edit_provision(edit(scope="single",planned_value="150.35"))["p_planned_value"]==150.35


def test_fixed_must_have_amount_and_variable_never_accepts_zero_or_invalid():
    for raw in (None,""):
        with pytest.raises(HTTPException):
            provisions.clean_provision(base(planned_value=raw,value_mode="fixed"))
        with pytest.raises(HTTPException):
            provisions.clean_edit_provision(edit(planned_value=raw,value_mode="fixed"))
    for raw in (0,-5,"nan","20.456","Infinity"):
        with pytest.raises(HTTPException):
            provisions.clean_provision(base(planned_value=raw))
        with pytest.raises(HTTPException):
            provisions.clean_edit_provision(edit(planned_value=raw))


def test_migration_propagates_only_forward_and_keeps_paid_history():
    sql=MIGRATION.read_text()
    assert "ALTER COLUMN planned_value DROP NOT NULL" in sql
    assert "axora_rule_fixed_requires_amount" in sql
    assert "CASE WHEN rev.id IS NOT NULL THEN rev.planned_value ELSE r.planned_value END" in sql
    assert "AFTER UPDATE OF status" in sql
    assert "NEW.status='paid'" in sql and "OLD.status='open'" in sql
    assert "i.sequence_no>NEW.sequence_no AND i.status='open'" in sql
    assert "AND value_mode='variable'" in sql
    assert "AND status='paid'" in sql  # Superseding later payments take priority
    assert "o.value_mode='fixed'" in sql  # Reconciliation with variable amount
    assert "o.effective_mode='fixed'" in sql  # Existing Record links
    assert "DROP TABLE" not in sql.upper()
    assert "TRUNCATE" not in sql.upper()
    assert "DELETE FROM" not in sql.upper()


def test_ui_shows_undefined_value_and_protects_history():
    html=(ROOT/"static/index.html").read_text()
    js=(ROOT/"static/provisions.js").read_text()
    assert 'id="pv-value-help"' in html
    assert 'id="pve-value-help"' in html
    assert "provision-variable-payment-note" in html
    assert "A definir" in js
    assert "provisionUnknown" in js
    assert 'item.planned_value==null?"":Number(item.planned_value).toFixed(2)' in js
    assert 'values.planned_value===""?null:Number(values.planned_value)' in js
    assert 'v=axora-pix-methods-r1' in html
