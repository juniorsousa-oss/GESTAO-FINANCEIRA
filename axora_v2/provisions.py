"""Cadastro seguro de compromissos financeiros: fase inicial de homologação.

Não modifica saldos automaticamente e não apaga registros legados.
Quitações são atômicas via RPC SQL, criando finance_movements.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
from fastapi import HTTPException
from urllib.parse import urlsplit
import re

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


def clean_payment_url(value):
    """Somente links externos HTTPS válidos; vazio remove o link da série."""
    if value is None or value == "":
        return None
    if not isinstance(value, str) or len(value) > 2048 or value != value.strip():
        raise HTTPException(422, "Link inválido. Informe uma URL HTTPS completa.")
    if any(ch.isspace() or ord(ch) < 32 or ch in "\\<>\"'" for ch in value):
        raise HTTPException(422, "O link contém caracteres não permitidos.")
    try:
        u = urlsplit(value)
        hostname = u.hostname or ""
        valid_port = u.port is None or u.port == 443
    except ValueError:
        raise HTTPException(422, "Link inválido. Confira o endereço informado.") from None
    if (u.scheme != "https" or not hostname or u.username or u.password
        or not valid_port or len(value) < 12
        or not re.fullmatch(r"(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\\.)+[a-zA-Z]{2,63}", hostname)
        or u.netloc.endswith(".")):
        raise HTTPException(422, "Use um endereço HTTPS público, como https://www.exemplo.com.br.")
    return value


def clean_provision(payload):
    if not isinstance(payload, dict):
        raise HTTPException(422, "Cadastro de provisão inválido.")
    allowed = {"description", "category", "responsible", "start_due_date", "planned_value",
               "value_mode", "recurrence", "frequency", "end_date", "installment_count", "payment_url"}
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
    if "payment_url" in payload:
        result["p_payment_url"] = clean_payment_url(payload["payment_url"])
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
    if not isinstance(payload, dict) or (
        set(payload) - {"scope", "due_date", "description", "category", "responsible", "planned_value", "value_mode", "payment_url"}
        or not {"scope", "due_date", "description", "category", "responsible", "planned_value", "value_mode"} <= set(payload)
    ):
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
    result = {"p_scope": scope,
              "p_due_date": valid_date(payload["due_date"], "Vencimento"),
              "p_planned_value": positive_money(payload["planned_value"], "Valor previsto"),
              "p_value_mode": payload["value_mode"], **details}
    if "payment_url" in payload:
        result["p_payment_url"] = clean_payment_url(payload["payment_url"])
    return result

# Sugestões supervisionadas de lançamentos já existentes:
# mesmo valor e data aproximada; nenhuma ação financeira nesta busca.
from difflib import SequenceMatcher
from axora_v2 import banking


def payment_matches(occurrence, payment_date, amount, bank_transactions, movements,
                    learning=None):
    """Candidatos de extrato/Registros, sem compensação ou quitação automática."""
    target = banking.normalize(occurrence["description"])
    target_amount = positive_money(amount)
    payment_on = date.fromisoformat(valid_date(payment_date, "Data do pagamento"))
    options = []
    for kind, records in (("bank", bank_transactions), ("movement", movements)):
        for entry in records:
            if kind == "bank":
                if entry.get("status") != "pending" or float(entry.get("amount") or 0) >= 0:
                    continue
                raw_value = abs(float(entry["amount"]))
                description = str(entry.get("description") or "")
                on = entry.get("posted_on")
                learned = banking.learned_targets(description, learning or {}).get(target, 0)
            else:
                if entry.get("classification") != "SAÍDA" or entry.get("provision_occurrence_id"):
                    continue
                raw_value = float(entry.get("value") or 0)
                description = str(entry.get("description") or "")
                on = entry.get("movement_date")
                learned = 0
            if abs(raw_value - target_amount) > 0.01:
                continue
            try:
                days = abs((date.fromisoformat(str(on)) - payment_on).days)
            except (ValueError, TypeError):
                continue
            if days > 45:
                continue
            similarity = SequenceMatcher(None, banking.normalize(description), target).ratio()
            # "PIX ... CEMIG" deve casar com "CEMIG", mesmo quando o
            # nome da concessionária é uma pequena parte do texto bancário.
            common = banking.bank_signature(description) & banking.bank_signature(
                occurrence["description"])
            merchant_match = any(len(word)>=5 for word in common)
            if similarity < 0.24 and not learned and not merchant_match:
                continue
            confidence = min(100, round(52 + max(0, 24-days*2) +
                                         similarity*22 + (16 if merchant_match else 0) +
                                         min(32, learned*25)))
            reasons = ["valor igual"]
            if merchant_match:
                reasons.append("favorecido identificado na descrição")
            if days <= 3:
                reasons.append("data próxima")
            if similarity >= .5:
                reasons.append("descrição semelhante")
            if learned:
                reasons.append("padrão confirmado anteriormente")
            options.append({
                "kind": kind, "id": int(entry["id"]), "description": description,
                "date": str(on), "amount": raw_value, "confidence": confidence,
                "reasons": reasons, "account_id": entry.get("account_id"),
                "learned": bool(learned),
            })
    return sorted(options, key=lambda x: (-x["confidence"], x["kind"], x["id"]))[:8]


def clean_match(payload):
    if not isinstance(payload, dict) or set(payload) != {"kind", "source_id"}:
        raise HTTPException(422, "Selecione um lançamento existente.")
    if payload["kind"] not in {"bank", "movement"}:
        raise HTTPException(422, "Origem inválida.")
    return {"kind": payload["kind"], "source_id": banking.positive_id(payload["source_id"])}
