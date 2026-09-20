"""Perfil de exibição local à sessão Streamlit.

A V1 usa uma senha compartilhada: o nome informado não autentica uma
identidade individual. A foto é opcional e não é enviada ao banco.
"""

import base64
from typing import Any

MAX_AVATAR_BYTES = 1_000_000


def clean_display_name(value: str) -> str:
    """Normaliza espaços e limita o texto visível no cabeçalho."""
    return " ".join(str(value or "").split())[:40]


def avatar_data_uri(uploaded: Any) -> str:
    """Aceita somente pequenos PNG/JPEG para renderizar em uma tag <img>."""
    payload = uploaded.getvalue()
    if not payload or len(payload) > MAX_AVATAR_BYTES:
        raise ValueError("A foto deve ter até 1 MB.")
    if payload.startswith(b"\x89PNG\\r\\n\x1a\\n"):
        mime = "image/png"
    elif payload.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    else:
        raise ValueError("Selecione uma imagem válida em PNG ou JPEG.")
    return "data:" + mime + ";base64," + base64.b64encode(payload).decode("ascii")
