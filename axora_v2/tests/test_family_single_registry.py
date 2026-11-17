"""Regressões: cadastro familiar único, classes e privacidade dos secundários."""
from pathlib import Path
from fastapi import HTTPException
import pytest
from axora_v2 import banking, family_policy, family_routes

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "static"
ROLES = ("conjuge", "pai", "mae", "filho", "sogro", "tio", "outro")


def test_one_registration_form_lives_only_in_settings():
    family = (WEB / "family.js").read_text()
    app = (WEB / "app.js").read_text()
    page = family.split("function pageHtml(){", 1)[1].split("async function saveProfile", 1)[0]
    settings = family.split("function settingsPanel(){", 1)[1].split("function pageHtml(){", 1)[0]
    assert 'newProfileForm()' in settings
    assert 'newProfileForm()' not in page
    assert 'panel("Cadastro familiar e acessos"' in app
    assert 'AxoraFamily.settingsPanel()' in app
    assert 'me?.family_enabled && window.AxoraFamily' in app
    assert 'bankingHolderCatalogPanel()' in app  # only non-family fallback
    assert 'data-family-action="activate-bank-member"' in settings
    assert 'data-family-action="activate-bank-member"' not in page


def test_family_cards_use_contextual_three_dot_menu():
    js = (WEB / "family.js").read_text()
    css = (WEB / "family.css").read_text()
    assert 'details class="family-member-menu axora-action-menu" data-family-profile-id=' in js
    assert 'data-family-profile-id' in js
    assert 'aria-label="Opções do membro ' in js
    assert 'data-family-action="save-relationship"' in js
    assert 'data-family-action="enable-login"' in js
    assert '.family-member-menu-panel' in css
    assert '.family-member-menu[open]' in css
    assert 'expandedFamilyMenus' in (WEB / "app.js").read_text()


@pytest.mark.parametrize("role", ROLES)
def test_consistent_relationships_in_family_and_bank(role):
    assert family_routes._role(role) == role
    assert banking.clean_holder({"name": "Perfil de teste", "relationship": role})["relationship"] == role
    assert role in family_policy.ROLES
    assert f'["{role}",' in (WEB / "family.js").read_text()
    assert f'value="{role}"' in (WEB / "index.html").read_text()


@pytest.mark.parametrize("role", ("pai", "mae", "sogro", "tio", "outro"))
def test_secondary_kinship_does_not_inherit_family_wide_visibility(role):
    params = dict(viewer_id=22, principal_id=1, creator_id=1,
                  viewer_role=role, label="familia", same_workspace=True)
    assert not family_policy.can_view(**params)
    assert family_policy.can_view(**{**params, "label": "selecionados",
                                    "allowed_user_ids": (22,)})
    assert not family_policy.can_view(**{**params, "label": "selecionados",
                                        "allowed_user_ids": (23,)})


def test_beta_migration_is_isolated_and_links_member_atomically():
    sql = (ROOT / "migrations" / "20261117_family_single_registry.sql").read_text()
    assert "BEGIN;" in sql and "COMMIT;" in sql
    assert "ALTER TABLE axora_beta.finance_family_profiles" in sql
    assert "ALTER TABLE axora_beta.finance_bank_holders" in sql
    assert "family_profile_id" in sql
    assert "p_profile_id IS NULL" in sql
    assert "INSERT INTO axora_beta.finance_bank_holders" in sql
    assert "axora_family_upsert_member" in sql
    assert "axora_family_change_relationship" in sql
    assert "ALTER TABLE public." not in sql
    assert "GRANT EXECUTE" in sql
