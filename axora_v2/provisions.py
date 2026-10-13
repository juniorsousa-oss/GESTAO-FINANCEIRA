"""Cadastro seguro de compromissos financeiros: fase inicial de homologação.

Não modifica saldos automaticamente e não apaga registros legados.
Quitações são atômicas via RPC SQL, criando finance_movements.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
from fastapi import HTTPException

RECURRENCE = {"once", "unlimited", "until_date", "installments"}
FREQUENCY = {"weekly", "biweekly", "monthly", "bimonthly", "quarterly", "semiannual", "yearly"}
VALUE_MODE = {"fixed", "variable"}


def positive_money(value, field="Valor"):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount <= 0 or amount > Decimal("999999999999.99"):
            raise InvalidOperation
        if amount.as_tuple().exponent < -2:
            raise InvalidOperation
    except (InvalidOperation, ValueError, TypeError):
        raise HTTPException(422, f"{field} deve ser positivo, com até duas casas decimais.") from None
    return float(amount)


def valid_date(value, field):
    try:
        return date.fromisoformat(str(value)).isoformat()
    except (ValueError, TypeError):
        raise HTTPException(422, f"{field} inválida.") from None


def clean_provision(payload):
    if not isinstance(payload, dict):
        raise HTTPException(422, "Cadastro de provisão inválido.")
    allowed = {"description", "category", "responsible", "start_due_date", "planned_value",
               "value_mode", "recurrence", "frequency", "end_date", "installment_count"}
    if set(payload) - allowed:
        raise HTTPException(422, "Campos não reconhecidos para provisões.")

    result = {}
    for field, label in (("description", "Descrição"), ("category", "Categoria"), ("responsible", "Responsável")):
        value = payload.get(field)
        if not isinstance(value, str) or not (1 <= len(value.strip()) <= (240 if field == "description" else 120)):
            raise HTTPException(422, f"{label} é obrigatório.")
        result["p_" + field] = value.strip()

    result["p_start_due_date"] = valid_date(payload.get("start_due_date"), "Data de vencimento")
    result["p_planned_value"] = positive_money(payload.get("planned_value"), "Valor previsto")
    recurrence = payload.get("recurrence")
    frequency = payload.get("frequency", "monthly")
    value_mode = payload.get("value_mode", "fixed")
    if recurrence not in RECURRENCE:
        raise HTTPException(422, "Escolha o tipo de recorrência.")
    if frequency not in FREQUENCY or value_mode not in VALUE_MODE:
        raise HTTPException(422, "Periodicidade ou natureza do valor inválida.")

    result.update(p_recurrence=recurrence, p_frequency=frequency, p_value_mode=value_mode,
                  p_end_date=None, p_installment_count=None)
    if recurrence == "until_date" and payload.get("end_date"):
        # Compatibilidade com uma eventual integração antiga; o novo formulário usa quantidade.
        end_date = valid_date(payload["end_date"], "Data final")
        if end_date < result["p_start_due_date"]:
            raise HTTPException(422, "A data final deve ser posterior ao primeiro vencimento.")
        result["p_end_date"] = end_date
    if recurrence in ("until_date", "installments") and not result["p_end_date"]:
        value = payload.get("installment_count")
        if isinstance(value, bool) or not str(value).isdigit() or not (1 <= int(value) <= 360):
            raise HTTPException(422, "Informe de 1 a 360 vencimentos ou parcelas.")
        result["p_installment_count"] = int(value)
    return result


def clean_payment(payload):
    if not isinstance(payload, dict) or set(payload) != {"payment_date", "amount"}:
        raise HTTPException(422, "Informe data efetiva e valor pago.")
    return {"p_payment_date": valid_date(payload.get("payment_date"), "Data do pagamento"),
            "p_amount": positive_money(payload.get("amount"), "Valor pago")}


def clean_scope(value):
    if value not in ("single", "future"):
        raise HTTPException(422, "Escolha apenas este vencimento ou este e os próximos.")
    return value


def clean_edit_provision(payload):
    if not isinstance(payload, dict) or set(payload) != {
        "scope", "due_date", "description", "category", "responsible", "planned_value", "value_mode"
    }:
        raise HTTPException(422, "Informe todos os campos da edição e seu alcance.")
    scope = clean_scope(payload["scope"])
    details = {}
    for field, max_length in (("description", 240), ("category", 120), ("responsible", 120)):
        value = payload.get(field)
        if not isinstance(value, str) or not (1 <= len(value.strip()) <= max_length):
            raise HTTPException(422, f"{field.capitalize()} inválido.")
        details["p_" + field] = value.strip()
    if payload["value_mode"] not in VALUE_MODE:
        raise HTTPException(422, "Natureza do valor inválida.")
    return {"p_scope": scope,
            "p_due_date": valid_date(payload["due_date"], "Vencimento"),
            "p_planned_value": positive_money(payload["planned_value"], "Valor previsto"),
            "p_value_mode": payload["value_mode"], **details}
