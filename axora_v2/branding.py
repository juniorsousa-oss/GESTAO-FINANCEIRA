"""Normalização segura da assinatura institucional compartilhada do AXORA."""
import base64
import io

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD = 5 * 1024 * 1024
MAX_PIXELS = 12_000_000
MAX_OPTIMIZED = 1_050_000
SUPPORTED = {"image/png", "image/jpeg", "image/webp"}


def prepare_logo(raw: bytes, declared_type: str) -> tuple[str, str]:
    """Decodifica, reduz e reconstrói a imagem, eliminando metadados do arquivo."""
    if declared_type not in SUPPORTED:
        raise HTTPException(422, "Use PNG, JPG ou WebP. Para SVG, exporte primeiro em PNG transparente.")
    if not raw or len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "A imagem precisa ter até 5 MB.")

    try:
        with Image.open(io.BytesIO(raw)) as opened:
            if opened.format not in {"PNG", "JPEG", "WEBP"}:
                raise HTTPException(422, "Arquivo não corresponde a PNG, JPG ou WebP.")
            if opened.width * opened.height > MAX_PIXELS:
                raise HTTPException(422, "Imagem muito grande. Limite de 12 megapixels.")
            img = ImageOps.exif_transpose(opened)
            has_alpha = img.mode in ("RGBA", "LA") or (
                img.mode == "P" and "transparency" in img.info
            )
            img = img.convert("RGBA" if has_alpha else "RGB")
            img.thumbnail((1600, 1000), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            img.save(output, format="WEBP", lossless=True, method=5)
            if output.tell() > MAX_OPTIMIZED:
                output = io.BytesIO()
                img.save(output, format="WEBP", quality=93, method=5)
            data = output.getvalue()
    except HTTPException:
        raise
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        raise HTTPException(422, "Imagem inválida ou corrompida.") from None

    if len(data) > MAX_OPTIMIZED:
        raise HTTPException(422, "Não foi possível otimizar esta imagem. Envie uma logo menor.")
    return "image/webp", "data:image/webp;base64," + base64.b64encode(data).decode("ascii")


def decode_logo(data_uri: str) -> bytes:
    prefix = "data:image/webp;base64,"
    if not data_uri.startswith(prefix):
        raise HTTPException(500, "Assinatura institucional inválida.")
    try:
        return base64.b64decode(data_uri[len(prefix):], validate=True)
    except (ValueError, base64.binascii.Error):
        raise HTTPException(500, "Assinatura institucional inválida.") from None
