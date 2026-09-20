from __future__ import annotations

import streamlit as st

from services.profile import avatar_data_uri, clean_display_name
from services.db import get_settings, is_configured, save_setting


def render():
    if is_configured():
        st.success("Banco financeiro validado em leitura. Acesso persistente protegido pela senha da sessão.")
    else:
        st.warning(
            "Modo de teste — sem banco persistente. Os registros desta sessão "
            "não migram automaticamente quando o Supabase for habilitado."
        )
        st.info(
            "Para conectar um projeto financeiro privado, prepare as cinco tabelas "
            "do supabase_schema.sql e defina SUPABASE_URL, SUPABASE_KEY e "
            "APP_ACCESS_PASSWORD nos Secrets do Streamlit Cloud. "
            "Nunca compartilhe essas credenciais no chat ou no GitHub."
        )

    st.subheader("Meu perfil")
    st.caption(
        "O nome e a foto são de exibição nesta sessão. A versão atual "
        "ainda usa uma senha compartilhada, sem contas individuais."
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
            st.session_state["_gf_display_name"] = normalized
            st.rerun()

    avatar_file = st.file_uploader(
        "Foto de perfil (PNG ou JPEG, até 1 MB)",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=False,
        key="gf_profile_photo",
    )
    col_save, col_remove = st.columns(2)
    if col_save.button(
        "Aplicar foto",
        key="gf_profile_apply_photo",
        disabled=avatar_file is None,
        use_container_width=True,
    ):
        try:
            st.session_state["_gf_avatar_uri"] = avatar_data_uri(avatar_file)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.rerun()
    if col_remove.button(
        "Remover foto",
        key="gf_profile_remove_photo",
        use_container_width=True,
    ):
        st.session_state.pop("_gf_avatar_uri", None)
        st.rerun()
    st.caption(
        "A foto fica somente nesta sessão e não é enviada ao Supabase. "
        "Para mantê-la após um novo login, será necessário armazenamento "
        "de perfis individuais em uma versão futura."
    )
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
