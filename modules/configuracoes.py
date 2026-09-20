from __future__ import annotations

import streamlit as st

from services.profile import avatar_data_uri, clean_display_name
from services.db import get_settings, is_configured, save_setting
from services.users import create_user, list_users, update_own_profile


def render():
    if is_configured():
        st.success("Banco financeiro conectado. Acesso associado ao usuário identificado pela senha.")
    else:
        st.warning(
            "Modo de teste — sem banco persistente. Os registros desta sessão "
            "não migram automaticamente quando o Supabase for habilitado."
        )
        st.info(
            "Para conectar um projeto financeiro privado, prepare as seis tabelas "
            "do supabase_schema.sql e defina SUPABASE_URL, SUPABASE_KEY e "
            "APP_ACCESS_PASSWORD (senha inicial do administrador) nos Secrets do Streamlit Cloud. "
            "Nunca compartilhe essas credenciais no chat ou no GitHub."
        )

    if is_configured() and st.button(
        "Sair / trocar usuário",
        key="gf_logout_button",
        help="Encerra a sessão atual e volta à tela de senha.",
    ):
        # Não limpar outros dados financeiros persistidos no banco.
        for key in (
            "_gf_authenticated", "_gf_user_id", "_gf_display_name",
            "_gf_is_admin", "_gf_avatar_uri", "_gf_db_verified",
            "_gf_login_failures", "_gf_login_error", "_gf_lock_until",
        ):
            st.session_state.pop(key, None)
        st.rerun()

    st.subheader("Meu perfil")
    st.caption(
        "O nome e a foto deste perfil são associados à sua senha de acesso."
    )
    current_name = st.session_state.get("_gf_display_name", "")
    display_name = st.text_input(
        "Nome no cabeçalho",
        value=current_name,
        max_chars=40,
        key="gf_profile_name_input",
    )
    if st.button("Atualizar nome", key="gf_profile_save_name"):
        normalized = clean_display_name(display_name)
        if not normalized:
            st.warning("Informe um nome para exibir no cabeçalho.")
        else:
            try:
                if is_configured():
                    update_own_profile(
                        int(st.session_state["_gf_user_id"]),
                        {"display_name": normalized},
                    )
                st.session_state["_gf_display_name"] = normalized
                st.rerun()
            except Exception:
                st.error("Não foi possível salvar o nome no perfil.")

    avatar_file = st.file_uploader(
        "Foto de perfil (PNG ou JPEG, até 15 MB)",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=False,
        key="gf_profile_photo",
    )
    st.caption(
        "Fotos maiores são redimensionadas automaticamente para uma miniatura "
        "leve antes de serem salvas. A imagem original não fica armazenada no banco."
    )
    col_save, col_remove = st.columns(2)
    if col_save.button(
        "Aplicar foto",
        key="gf_profile_apply_photo",
        disabled=avatar_file is None,
        use_container_width=True,
    ):
        try:
            photo = avatar_data_uri(avatar_file)
            if is_configured():
                update_own_profile(
                    int(st.session_state["_gf_user_id"]),
                    {"avatar_data_uri": photo},
                )
            st.session_state["_gf_avatar_uri"] = photo
        except ValueError as exc:
            st.error(str(exc))
        except Exception:
            st.error("Não foi possível salvar a foto no perfil.")
        else:
            st.rerun()
    if col_remove.button(
        "Remover foto",
        key="gf_profile_remove_photo",
        use_container_width=True,
    ):
        try:
            if is_configured():
                update_own_profile(
                    int(st.session_state["_gf_user_id"]),
                    {"avatar_data_uri": None},
                )
            st.session_state.pop("_gf_avatar_uri", None)
            st.rerun()
        except Exception:
            st.error("Não foi possível remover a foto do perfil.")
    st.caption(
        "A foto é armazenada no perfil privado e será carregada no próximo login."
        if is_configured() else "No modo de teste, a foto permanece somente nesta sessão."
    )
    st.divider()

    if is_configured() and st.session_state.get("_gf_is_admin"):
        st.subheader("Gerenciar usuários")
        st.caption(
            "Cada usuário possui uma senha própria. Ao entrar, o aplicativo "
            "carrega automaticamente seu nome e sua foto."
        )
        st.warning(
            "Atenção: nesta versão, todos os usuários cadastrados têm acesso "
            "à MESMA base de movimentações, contas, previsões e dívidas. "
            "Os dados financeiros ainda não são separados por usuário."
        )
        with st.expander("Usuários cadastrados"):
            try:
                accounts = list_users()
                st.dataframe(
                    [
                        {
                            "Nome": account["display_name"],
                            "Perfil": "Administrador" if account["is_admin"] else "Usuário",
                            "Situação": "Ativo" if account["is_active"] else "Inativo",
                        }
                        for account in accounts
                    ],
                    hide_index=True,
                    use_container_width=True,
                )
            except Exception:
                st.error("Não foi possível consultar os usuários cadastrados.")

        with st.form("gf_create_user_form", clear_on_submit=True):
            new_name = st.text_input(
                "Nome do novo usuário", max_chars=40, key="gf_new_user_name"
            )
            new_password = st.text_input(
                "Senha exclusiva do novo usuário (mínimo de 12 caracteres)",
                type="password", key="gf_new_user_password"
            )
            password_confirmation = st.text_input(
                "Confirmar senha do novo usuário",
                type="password", key="gf_new_user_password_confirm"
            )
            accepts_sharing = st.checkbox(
                "Estou ciente de que esse usuário poderá visualizar e alterar "
                "a mesma base financeira."
            )
            register = st.form_submit_button(
                "Cadastrar usuário", use_container_width=True
            )
        if register:
            if not accepts_sharing:
                st.warning("Confirme o compartilhamento dos dados para continuar.")
            elif new_password != password_confirmation:
                st.error("As senhas digitadas não são iguais.")
            else:
                try:
                    created = create_user(new_name, new_password)
                    st.success(
                        f"Usuário {created['display_name']} cadastrado. "
                        "A nova senha já pode ser utilizada na tela inicial."
                    )
                except ValueError as exc:
                    st.warning(str(exc))
                except Exception:
                    st.error("Não foi possível cadastrar o usuário.")
        st.divider()

    settings = get_settings()
    st.subheader("Metas")
    with st.form("financial_settings"):
        c1, c2 = st.columns(2)
        gross = c1.number_input("Renda bruta mensal (R$)", min_value=0.0, value=float(settings["gross_income"]), step=100.0)
        net = c2.number_input("Renda líquida mensal (R$)", min_value=0.0, value=float(settings["net_income"]), step=100.0)
        c1, c2, c3 = st.columns(3)
        emergency = c1.number_input("Reserva: meses de renda", min_value=1.0, value=float(settings["emergency_months"]), step=1.0)
        investment = c2.number_input("Investimento mensal (%)", min_value=0.0, max_value=100.0, value=float(settings["investment_pct"]), step=1.0)
        fixed = c3.number_input("Contas fixas (%)", min_value=0.0, max_value=100.0, value=float(settings["fixed_pct"]), step=1.0)
        c1, c2 = st.columns(2)
        leisure = c1.number_input("Lazer (%)", min_value=0.0, max_value=100.0, value=float(settings["leisure_pct"]), step=1.0)
        multiple = c2.number_input("Meta patrimônio (x renda líquida)", min_value=0.0, value=float(settings["investment_multiple"]), step=10.0)
        submitted = st.form_submit_button("Salvar configurações", use_container_width=True)
    if submitted:
        values = {
            "gross_income": gross, "net_income": net, "emergency_months": emergency,
            "investment_pct": investment, "fixed_pct": fixed, "leisure_pct": leisure,
            "investment_multiple": multiple,
        }
        try:
            for key, value in values.items():
                save_setting(key, float(value))
            st.success("Configurações salvas.")
            st.rerun()
        except Exception as exc:
            st.error(f"Não foi possível salvar: {exc}")

    st.divider()
    st.subheader("Escopo da V1")
    st.markdown("""
- Dashboard consolidado do realizado, previsto, saldos e dívidas.
- Cadastro de movimentações realizadas.
- Agenda de contas/entradas previstas e atualização de status.
- Conferência de contas e saldos.
- Controle de dívidas.
- Importação das quatro bases financeiras principais do Excel.
- Supermercado, Unimed e demais módulos auxiliares ficam preparados para as próximas versões.
""")
