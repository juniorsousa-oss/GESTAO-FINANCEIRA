"""Normalização segura da assinatura institucional compartilhada do AXORA."""
import base64
import io

from fastapi import HTTPException
from PIL import Image, ImageChops, ImageOps, UnidentifiedImageError

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
            img = trim_logo_margins(img)
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


def trim_logo_margins(image: Image.Image) -> Image.Image:
    """Remove margens transparentes (ou brancas) em excesso, sem deformar a arte.

    Mantem um pequeno respiro ao redor; logos já ajustadas nao sao alteradas.
    """
    image = image.convert("RGBA")
    alpha = image.getchannel("A")
    alpha_extent = alpha.getextrema()
    if alpha_extent[0] < 255:
        mask = alpha.point(lambda a: 255 if a > 15 else 0)
        bounds = mask.getbbox()
    else:
        # So considera fundo branco uniforme se todos os cantos forem claros.
        corners = [
            image.getpixel((0, 0)), image.getpixel((image.width - 1, 0)),
            image.getpixel((0, image.height - 1)),
            image.getpixel((image.width - 1, image.height - 1)),
        ]
        if all(min(pixel[:3]) >= 245 for pixel in corners):
            rgb = image.convert("RGB")
            difference = ImageChops.difference(
                rgb, Image.new("RGB", rgb.size, (255, 255, 255))
            )
            mask = difference.convert("L").point(lambda value: 255 if value > 24 else 0)
            bounds = mask.getbbox()
        else:
            bounds = None
    if bounds is None:
        return image

    left, top, right, bottom = bounds
    content_w, content_h = right - left, bottom - top
    if content_w < 3 or content_h < 3:
        return image
    # Proteger a proporcao, inclusive para logos horizontais.
    pad_x = max(2, round(content_w * 0.035))
    pad_y = max(2, round(content_h * 0.16))
    crop = (
        max(0, left - pad_x),
        max(0, top - pad_y),
        min(image.width, right + pad_x),
        min(image.height, bottom + pad_y),
    )
    if crop == (0, 0, image.width, image.height):
        return image
    return image.crop(crop)


def trim_icon_margins(image: Image.Image) -> Image.Image:
    """Corta a área transparente externa ao ícone, inclusive sombras difusas.

    Para ícones pequenos, uma borda de 20% torna o símbolo quase ilegível.
    Usa o desenho visível (opacidade >= 64), sem fazer qualquer alongamento.
    """
    image = image.convert("RGBA")
    alpha = image.getchannel("A")
    if alpha.getextrema()[0] == 255:
        return image  # Sem transparência: não inventar recortes em arte opaca.
    bounds = alpha.point(lambda a: 255 if a >= 64 else 0).getbbox()
    if bounds is None:
        raise HTTPException(422, "Imagem sem conteúdo visível.")
    left, top, right, bottom = bounds
    if right - left < 16 or bottom - top < 16:
        raise HTTPException(422, "Ícone muito pequeno.")
    return image.crop(bounds)


def render_square_icon(data_uri: str, size: int = 256) -> bytes:
    """Produz um favicon PNG quadrado de arte ampliada e proporção preservada."""
    raw = decode_logo(data_uri)
    try:
        with Image.open(io.BytesIO(raw)) as opened:
            image = trim_icon_margins(ImageOps.exif_transpose(opened))
            width, height = image.size
            if width < 16 or height < 16 or not .76 <= width / height <= 1.32:
                raise HTTPException(422, "Esta imagem não é um ícone quadrado.")
            # O símbolo ocupa até 98% do canvas; antes usava 91% mais
            # as margens internas da imagem enviada.
            bound = max(1, round(size * .98))
            image.thumbnail((bound, bound), Image.Resampling.LANCZOS)
            output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            output.alpha_composite(image, ((size - image.width)//2, (size - image.height)//2))
            buffer = io.BytesIO()
            output.save(buffer, "PNG", optimize=True)
            return buffer.getvalue()
    except HTTPException:
        raise
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        raise HTTPException(422, "Ícone inválido ou corrompido.") from None


def validate_square_upload(raw: bytes) -> None:
    """Proíbe logos horizontais nos slots quadrados (app icon e favicon)."""
    try:
        with Image.open(io.BytesIO(raw)) as opened:
            if opened.width * opened.height > MAX_PIXELS:
                raise HTTPException(422, "Imagem muito grande. Limite de 12 megapixels.")
            width, height = trim_icon_margins(ImageOps.exif_transpose(opened)).size
            if not .76 <= width / height <= 1.32:
                raise HTTPException(422, "O favicon e o ícone do aplicativo exigem uma imagem quadrada. Não envie a logo horizontal.")
    except HTTPException:
        raise
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError, ZeroDivisionError):
        raise HTTPException(422, "Imagem inválida.") from None


def render_logo_image(data_uri: str) -> bytes:
    """Reprocessa inclusive uploads anteriores, sem modificar o dado armazenado."""
    raw = decode_logo(data_uri)
    try:
        with Image.open(io.BytesIO(raw)) as opened:
            image = trim_logo_margins(opened)
            if image.size == opened.size:
                return raw
            out = io.BytesIO()
            image.save(out, "WEBP", lossless=True, method=5)
            return out.getvalue()
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        raise HTTPException(500, "Assinatura institucional invalida.") from None
