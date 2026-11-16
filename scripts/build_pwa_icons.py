"""Cria ícones PNG oficiais da marca AXORA sem alterar logos do produto."""
from pathlib import Path
import io
import cairosvg
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "axora_v2/static/axora-mark.svg"
OUTPUT = ROOT / "axora_v2/static/pwa"
OUTPUT.mkdir(parents=True, exist_ok=True)

for size in (192, 512):
    image = Image.open(io.BytesIO(cairosvg.svg2png(url=str(SOURCE), output_width=size, output_height=size))).convert("RGBA")
    path = OUTPUT / f"icon-{size}.png"
    image.save(path, format="PNG", optimize=True)
    assert Image.open(path).size == (size, size)
    print(path.relative_to(ROOT))
