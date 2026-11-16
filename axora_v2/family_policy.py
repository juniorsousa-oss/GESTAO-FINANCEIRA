"""Regras determinísticas da futura gestão familiar. Sem acesso direto à base.

IMPORTANTE: este módulo não substitui filtros de autorização de endpoints.
Até a migração e os filtros serem homologados, o compartilhamento continua desativado.
"""
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from fastapi import HTTPException

ROLES = frozenset({"principal", "conjuge", "filho", "outro"})
LABELS = frozenset({"privado", "casal", "familia", "selecionados"})
RESOURCE_KINDS = frozenset({"registro", "provisao", "conta", "transacao"})
MAX_CENTS = 10**14


def can_view(*, viewer_id, principal_id, creator_id, viewer_role,
             label, same_workspace, allowed_user_ids=()):
    """Negação por padrão; beneficiário do custo nunca implica direito de leitura."""
    if not same_workspace or viewer_role not in ROLES or label not in LABELS:
        return False
    if not isinstance(viewer_id, int) or viewer_id < 1:
        return False
    if viewer_id == principal_id or viewer_id == creator_id:
        return True
    if label == "casal":
        return viewer_role == "conjuge"
    if label == "familia":
        return viewer_role in {"conjuge", "filho"}
    if label == "selecionados":
        return viewer_id in set(allowed_user_ids)
    return False


def amount_cents(value, *, name="Valor"):
    if isinstance(value, bool):
        raise HTTPException(422, f"{name} inválido.")
    try:
        amount = Decimal(str(value))
        cents = amount * 100
        if not amount.is_finite() or cents != cents.to_integral_value() or cents <= 0 or cents > MAX_CENTS:
            raise InvalidOperation
        return int(cents)
    except (InvalidOperation, ValueError, TypeError):
        raise HTTPException(422, f"{name} deve ser positivo, com até duas casas decimais.") from None


def split_percentages(value, shares):
    """Distribui centavos restantes pelo maior resto; soma exata, sem centavo perdido."""
    total = amount_cents(value)
    if not isinstance(shares, list) or not (1 <= len(shares) <= 50):
        raise HTTPException(422, "Informe os participantes do rateio.")
    if any(not isinstance(item, dict) or set(item) != {"profile_id", "percentage"} for item in shares):
        raise HTTPException(422, "Rateio inválido.")
    profiles = [x["profile_id"] for x in shares]
    if any(type(v) is not int or v < 1 for v in profiles) or len(set(profiles)) != len(profiles):
        raise HTTPException(422, "Participantes inválidos ou duplicados.")
    try:
        percentages = [Decimal(str(x["percentage"])) for x in shares]
        if (any(not p.is_finite() or p <= 0 or p > 100 or p.as_tuple().exponent < -2 for p in percentages)
                or sum(percentages) != 100):
            raise InvalidOperation
    except (InvalidOperation, TypeError, ValueError):
        raise HTTPException(422, "O rateio deve somar exatamente 100%.") from None
    raw = [Decimal(total) * p / 100 for p in percentages]
    assigned = [int(p.to_integral_value(rounding=ROUND_FLOOR)) for p in raw]
    missing = total - sum(assigned)
    rank = sorted(range(len(shares)), key=lambda i: (-(raw[i] - assigned[i]), i))
    for i in rank[:missing]:
        assigned[i] += 1
    return [{"profile_id": profiles[i], "amount": f"{Decimal(assigned[i]) / 100:.2f}",
             "percentage": str(percentages[i])} for i in range(len(shares))]


def validate_payment_sources(value, payments, *, allowed_profile_ids):
    """Quem pagou é independente de quem se beneficiou do gasto."""
    total = amount_cents(value)
    if not isinstance(payments, list) or not (1 <= len(payments) <= 50):
        raise HTTPException(422, "Informe quem pagou.")
    valid = set(allowed_profile_ids)
    result = []
    seen = set()
    for item in payments:
        if not isinstance(item, dict) or set(item) != {"profile_id", "amount"}:
            raise HTTPException(422, "Origem de pagamento inválida.")
        profile = item["profile_id"]
        if type(profile) is not int or profile not in valid or profile in seen:
            raise HTTPException(422, "Pagador inexistente ou duplicado.")
        seen.add(profile)
        cents = amount_cents(item["amount"], name="Pagamento")
        result.append({"profile_id": profile, "amount": f"{Decimal(cents) / 100:.2f}"})
    if sum(amount_cents(x["amount"]) for x in result) != total:
        raise HTTPException(422, "Os pagamentos precisam somar exatamente o valor da despesa.")
    return result
