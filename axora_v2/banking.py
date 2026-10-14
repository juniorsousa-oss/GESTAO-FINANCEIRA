"""AXORA: titularidade, transações simuladas e sugestões explicáveis.

Nunca concilia sozinho e não acessa bancos; apenas transações registradas
manualmente pelo operador nesta primeira etapa.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
import unicodedata
import re

from fastapi import HTTPException

RELATIONSHIPS = {"proprio", "conjuge", "mae", "pai", "familiar", "outro"}
ACCOUNT_TYPES = {"corrente", "poupanca", "pagamento", "outro"}
ACTIONS = {"matched_record", "matched_provision", "recorded", "transfer", "ignored"}


def clean_text(value, label, limit=100, minimum=1):
    if not isinstance(value, str):
        raise HTTPException(422, f"{label} é obrigatório.")
    value = " ".join(value.strip().split())
    if len(value) < minimum or len(value) > limit or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise HTTPException(422, f"{label} inválido.")
    return value


def clean_holder(data):
    if not isinstance(data, dict) or set(data) != {"name", "relationship"}:
        raise HTTPException(422, "Informe o nome e o vínculo do titular.")
    if data["relationship"] not in RELATIONSHIPS:
        raise HTTPException(422, "Vínculo familiar inválido.")
    return {"name": clean_text(data["name"], "Titular"), "relationship": data["relationship"]}


def clean_account(data):
    required = {"holder_id", "bank_name", "nickname", "account_type"}
    if not isinstance(data, dict) or set(data) != required:
        raise HTTPException(422, "Preencha os dados obrigatórios da conta.")
    if data["account_type"] not in ACCOUNT_TYPES:
        raise HTTPException(422, "Tipo de conta inválido.")
    return {"holder_id": positive_id(data["holder_id"]),
            "bank_name": clean_text(data["bank_name"], "Banco", 80, 2),
            "nickname": clean_text(data["nickname"], "Apelido", 100, 2),
            "account_type": data["account_type"]}


def positive_id(value):
    if isinstance(value, bool) or not str(value).isdigit() or int(value) < 1:
        raise HTTPException(422, "Identificador inválido.")
    return int(value)


def money_abs(value):
    try:
        x = Decimal(str(value))
        if not x.is_finite() or x == 0 or abs(x) > Decimal("99999999999999.99") or x.as_tuple().exponent < -2:
            raise InvalidOperation
    except (TypeError, ValueError, InvalidOperation):
        raise HTTPException(422, "Valor deve ser diferente de zero e ter até duas casas decimais.") from None
    return float(x)


def clean_transaction(data):
    expected = {"account_id", "posted_on", "description", "amount"}
    if not isinstance(data, dict) or set(data) != expected:
        raise HTTPException(422, "Informe conta, data, descrição e valor.")
    try:
        value = date.fromisoformat(str(data["posted_on"])).isoformat()
    except (ValueError, TypeError):
        raise HTTPException(422, "Data bancária inválida.") from None
    return {"account_id": positive_id(data["account_id"]),
            "posted_on": value, "description": clean_text(data["description"], "Descrição", 240),
            "amount": money_abs(data["amount"]), "source": "manual"}


def clean_decision(data):
    if not isinstance(data, dict) or set(data) - {"transaction_id", "action", "target_id", "counterpart_id", "category", "reason"}:
        raise HTTPException(422, "Dados da decisão inválidos.")
    action = data.get("action")
    if action not in ACTIONS:
        raise HTTPException(422, "Escolha como tratar a movimentação.")
    result = {"p_transaction_id": positive_id(data.get("transaction_id")),
              "p_action": action, "p_target_id": None, "p_counterpart_id": None,
              "p_category": None, "p_reason": None}
    if action in {"matched_record", "matched_provision"}:
        result["p_target_id"] = positive_id(data.get("target_id"))
    elif action == "transfer":
        result["p_counterpart_id"] = positive_id(data.get("counterpart_id"))
    elif action == "recorded":
        result["p_category"] = clean_text(data.get("category"), "Categoria", 120)
    elif action == "ignored":
        result["p_reason"] = clean_text(data.get("reason"), "Justificativa", 250, 5)
    return result


def normalize(text):
    text = unicodedata.normalize("NFKD", str(text or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", text))


def score_match(transaction, candidate, *, candidate_type):
    """Pontuação informativa, jamais autorização de conciliação."""
    amount = float(transaction["amount"])
    target = float(candidate["amount"])
    if (amount < 0) != (target < 0):
        return None
    delta = abs(abs(amount) - abs(target))
    limit = max(0.01, abs(amount) * .06)
    if delta > limit:
        return None
    amount_points = 55 if delta < .011 else max(0, 30 * (1 - delta / limit))
    try:
        days = abs((date.fromisoformat(str(transaction["posted_on"])) -
                    date.fromisoformat(str(candidate["date"]))).days)
    except ValueError:
        days = 365
    date_points = 25 if days == 0 else max(0, 25 - days * 4)
    similarity = SequenceMatcher(None, normalize(transaction["description"]),
                                 normalize(candidate["description"])).ratio()
    text_points = round(similarity * 20, 2)
    score = round(amount_points + date_points + text_points)
    if score < 35:
        return None
    reasons = ["valor idêntico" if delta < .011 else "valor próximo, exige revisão"]
    if days <= 3:
        reasons.append("datas próximas")
    if similarity >= .55:
        reasons.append("descrição semelhante")
    return {"kind": candidate_type, "id": candidate["id"],
            "label": candidate["description"], "value": abs(target),
            "date": candidate["date"], "score": score,
            "strength": "Alta" if score >= 80 else "Média" if score >= 60 else "Baixa",
            "reasons": reasons, "can_confirm": delta < .011}


def suggestions(transaction, movements, occurrences, occupied=None):
    occupied = set(occupied or [])
    choices = []
    for m in movements:
        if m["id"] in occupied:
            continue
        direction = -1 if m.get("classification") == "SAÍDA" else 1
        match = score_match(transaction, {
            "id": m["id"], "amount": direction * float(m["value"]),
            "date": m.get("movement_date"), "description": m["description"],
        }, candidate_type="matched_record")
        if match:
            choices.append(match)
    if float(transaction["amount"]) < 0:
        for o in occurrences:
            match = score_match(transaction, {
                "id": o["id"], "amount": -float(o["planned_value"]),
                "date": o.get("due_date"),
                "description": o.get("description_override") or (o.get("rule") or {}).get("description", ""),
            }, candidate_type="matched_provision")
            if match:
                choices.append(match)
    return sorted(choices, key=lambda o: (-o["score"], o["kind"], o["id"]))[:6]
