"""Normalização de nomes e fotos por perfil individual.

Fotos originais de até 15 MB são redimensionadas e convertidas em JPEG
pequeno ANTES de serem persistidas no campo privado do Supabase.
"""

import base64
from io import BytesIO
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_IMAGE_PIXELS = 50_000_000
MAX_STORED_AVATAR_BYTES = 700_000
AVATAR_SIDE_PX = 480


def clean_display_name(value: str) -> str:
    """Normaliza espaços e limita o texto visível no cabeçalho."""
    return " ".join(str(value or "").split())[:40]


def avatar_data_uri(uploaded: Any) -> str:
    """Converte PNG/JPEG de até 15 MB em miniatura leve para o perfil."""
    if uploaded is None:
        raise ValueError("Selecione uma foto de perfil.")
    if getattr(uploaded, "size", 0) > MAX_UPLOAD_BYTES:
        raise ValueError("A foto original deve ter no máximo 15 MB.")
    payload = uploaded.getvalue()
    if not payload or len(payload) > MAX_UPLOAD_BYTES:
        raise ValueError("A foto original deve ter no máximo 15 MB.")

    try:
        with Image.open(BytesIO(payload)) as source:
            if source.format not in {"PNG", "JPEG"}:
                raise ValueError("Selecione uma foto válida em PNG ou JPEG.")
            if source.width * source.height > MAX_IMAGE_PIXELS:
                raise ValueError(
                    "A imagem possui resolução excessiva. Escolha uma foto menor."
                )
            # Corrige a orientação de fotos do celular antes da redução.
            image = ImageOps.exif_transpose(source)
            image.thumbnail((AVATAR_SIDE_PX, AVATAR_SIDE_PX), Image.Resampling.LANCZOS)
            # JPEG não suporta transparência: colocar fundo branco se necessário.
            if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
                alpha = image.convert("RGBA")
                thumbnail = Image.new("RGB", alpha.size, (255, 255, 255))
                thumbnail.paste(alpha, mask=alpha.getchannel("A"))
            else:
                thumbnail = image.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Não foi possível processar a foto. Use PNG ou JPEG válido.") from exc

    for quality in (85, 76, 66):
        output = BytesIO()
        thumbnail.save(output, format="JPEG", quality=quality, optimize=True)
        encoded_image = output.getvalue()
        if len(encoded_image) <= MAX_STORED_AVATAR_BYTES:
            data_uri = "data:image/jpeg;base64," + base64.b64encode(
                encoded_image
            ).decode("ascii")
            # Preserva o limite atual da coluna no Supabase (1.400.000).
            if len(data_uri) <= 1_400_000:
                return data_uri
    raise ValueError("Não foi possível reduzir a foto. Tente outra imagem.")
