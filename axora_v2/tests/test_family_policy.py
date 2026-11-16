"""Política de compartilhamento e rateio isolada, sem chamar banco financeiro real."""
import pytest
from fastapi import HTTPException
from axora_v2.family_policy import can_view, split_percentages, validate_payment_sources


def visible(viewer, role, label="privado", creator=1, workspace=True, allowed=()):
    return can_view(viewer_id=viewer, principal_id=1, creator_id=creator,
                    viewer_role=role, label=label, same_workspace=workspace, allowed_user_ids=allowed)


def test_principal_sees_everything_but_spouse_sees_only_own_or_shared():
    assert visible(1, "principal")
    assert visible(2, "conjuge", "privado", creator=2)
    assert not visible(2, "conjuge", "privado")
    assert visible(2, "conjuge", "casal")
    assert not visible(3, "filho", "casal")
    assert visible(3, "filho", "familia")
    assert not visible(4, "outro", "familia")
    assert visible(4, "outro", "selecionados", allowed=[4])
    assert not visible(4, "outro", "selecionados", allowed=[3])
    assert not visible(1, "principal", workspace=False)
    assert not visible(2, "conjuge", "rotulo_desconhecido")
    assert not visible(2, "conjuge", "casal", workspace=False)


def test_beneficiary_not_permission_and_no_implicit_visibility():
    # O beneficiário nem é argumento de can_view: rateio não abre acesso.
    split = split_percentages("300.00", [{"profile_id": 3, "percentage": 100}])
    assert split[0]["profile_id"] == 3
    assert not visible(3, "filho", "privado")
    assert not visible(3, "filho", "casal")


def test_rateio_100_percent_preserves_cents():
    result = split_percentages("100.00", [
        {"profile_id": 1, "percentage": 33.33},
        {"profile_id": 2, "percentage": 33.33},
        {"profile_id": 3, "percentage": 33.34}
    ])
    assert [x["amount"] for x in result] == ["33.33", "33.33", "33.34"]
    thirds = split_percentages("0.01", [
        {"profile_id": 1, "percentage": 33.33},
        {"profile_id": 2, "percentage": 33.33},
        {"profile_id": 3, "percentage": 33.34}
    ])
    assert [x["amount"] for x in thirds] == ["0.00", "0.00", "0.01"]


@pytest.mark.parametrize("parts", [
    [{"profile_id": 1, "percentage": 60}, {"profile_id": 2, "percentage": 30}],
    [{"profile_id": 1, "percentage": 50}, {"profile_id": 1, "percentage": 50}],
    [{"profile_id": 1, "percentage": 0}, {"profile_id": 2, "percentage": 100}],
])
def test_invalid_splits_fail_closed(parts):
    with pytest.raises(HTTPException) as exc:
        split_percentages("12.00", parts)
    assert exc.value.status_code == 422


def test_payment_split_is_distinct_from_cost_split():
    payments=validate_payment_sources("300.00", [
        {"profile_id": 1, "amount": "200.00"},
        {"profile_id": 2, "amount": "100.00"}], allowed_profile_ids={1, 2})
    assert sum(float(x["amount"]) for x in payments) == 300
    with pytest.raises(HTTPException):
        validate_payment_sources("300.00", [{"profile_id": 1, "amount": "299.00"}], allowed_profile_ids={1, 2})
    with pytest.raises(HTTPException):
        validate_payment_sources("300.00", [{"profile_id": 3, "amount": "300.00"}], allowed_profile_ids={1, 2})
