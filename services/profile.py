"""Validação de nome e foto de perfil individual do Gestão Financeira.

O nome/foto são associados no banco à conta cuja senha foi verificada.
O campo da foto recebe PNG ou JPEG e tem limite de 1 MB.
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
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif payload.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    else:
        raise ValueError("Selecione uma imagem válida em PNG ou JPEG.")
    return "data:" + mime + ";base64," + base64.b64encode(payload).decode("ascii")
