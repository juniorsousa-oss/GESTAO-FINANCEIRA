"""Diretório de usuários independente de permissões financeiras do AXORA BETA."""
from pathlib import Path

from axora_v2 import family_service

BASE=Path(__file__).resolve().parents[1]
W="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
PEOPLE=[
    {"id":10,"display_name":"Principal teste","relationship":"principal","linked_user_id":1,"active":True},
    {"id":20,"display_name":"Membro teste","relationship":"conjuge","linked_user_id":2,"active":True},
    {"id":30,"display_name":"Parente autorizado","relationship":"filho","linked_user_id":None,"active":True},
    {"id":40,"display_name":"Parente reservado","relationship":"mae","linked_user_id":None,"active":True},
    {"id":50,"display_name":"Membro selecionado","relationship":"pai","linked_user_id":3,"active":True},
]
TAGS={
    10:{"id":10,"creator_user_id":1,"label":"privado","granted_user_ids":[]},
    30:{"id":30,"creator_user_id":1,"label":"casal","granted_user_ids":[]},
    40:{"id":40,"creator_user_id":1,"label":"privado","granted_user_ids":[]},
    50:{"id":50,"creator_user_id":1,"label":"selecionados","granted_user_ids":[3]},
}


def test_directory_only_reveals_explicitly_permitted_members(monkeypatch):
    monkeypatch.setattr(family_service,"profiles",lambda _:PEOPLE)
    monkeypatch.setattr(family_service,"visibility_map",lambda ctx,kind,ids:TAGS if kind=="perfil" else {})
    spouse={"_family":{"workspace_id":W,"profile_id":20,"role":"conjuge",
                       "user_id":2,"owner_id":1}}
    result=family_service.directory_profiles(spouse)
    assert {x["id"] for x in result}=={20,30}
    assert all(set(x)=={"id","display_name","relationship","active"} for x in result)
    assert "Parente reservado" not in str(result)
    assert "Principal teste" not in str(result)
    assert "granted_user_ids" not in str(result)
    assert "linked_user_id" not in str(result)


def test_specific_grant_does_not_imply_access_to_other_profiles(monkeypatch):
    monkeypatch.setattr(family_service,"profiles",lambda _:PEOPLE)
    monkeypatch.setattr(family_service,"visibility_map",lambda ctx,kind,ids:TAGS)
    member={"_family":{"workspace_id":W,"profile_id":50,"role":"pai",
                       "user_id":3,"owner_id":1}}
    result=family_service.directory_profiles(member)
    assert [x["id"] for x in result]==[50]


def test_owner_can_configure_labels_and_selected_viewers(monkeypatch):
    monkeypatch.setattr(family_service,"profiles",lambda _:PEOPLE)
    monkeypatch.setattr(family_service,"visibility_map",lambda ctx,kind,ids:TAGS)
    owner={"_family":{"workspace_id":W,"profile_id":10,"role":"principal",
                      "user_id":1,"owner_id":1}}
    result=family_service.directory_profiles(owner)
    assert len(result)==5
    member=next(x for x in result if x["id"]==50)
    assert member["visibility_label"]=="selecionados"
    assert member["visibility_viewers"]==[3]
    default=next(x for x in result if x["id"]==20)
    assert default["visibility_label"]=="privado"
    assert default["visibility_viewers"]==[]


def test_acl_contract_and_ui_separate_directory_from_financial_access():
    route=(BASE/"family_routes.py").read_text()
    service=(BASE/"family_service.py").read_text()
    policy=(BASE/"family_policy.py").read_text()
    ui=(BASE/"static/family.js").read_text()
    html=(BASE/"static/index.html").read_text()
    migration=(BASE/"migrations/20261118_family_member_directory_privacy.sql").read_text()
    assert '"profiles": family_service.directory_profiles(user)' in route
    assert 'profiles = family_service.accessible_profiles(user)' in route  # financeiro isolado
    assert 'if ctx["role"] != "principal"' in route
    assert '"perfil": "finance_family_profiles"' in service
    assert 'visible(ctx, "perfil", x["id"]' in service
    assert '"perfil"' in policy
    assert 'data-resource="perfil"' in ui
    assert 'profile?.visibility_viewers||[]' in ui
    assert "Os dados financeiros desta pessoa permanecem privados" in ui
    assert 'id="family-visibility-heading"' in html
    assert "'perfil'" in migration
    assert 'finance_family_profiles' in migration
    assert 'REVOKE ALL ON FUNCTION' in migration
    assert 'GRANT EXECUTE' in migration
    assert 'axora_beta.' in migration
    assert 'TRUNCATE' not in migration
    assert 'DELETE FROM axora_beta.finance_family_profiles' not in migration
