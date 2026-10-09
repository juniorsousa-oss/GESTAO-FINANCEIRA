"""Assinatura institucional AXORA: upload admin, leitura pública e persistência simulada."""
import io
import base64

from fastapi.testclient import TestClient
from PIL import Image
from axora_v2 import db, security, branding
from axora_v2.main import app


def sample_image() -> bytes:
    image = Image.new("RGBA", (650, 200), (0, 0, 0, 0))
    for x in range(35, 520):
        for y in range(60, 160):
            image.putpixel((x, y), (12, 35, 60, 255))
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def test_institutional_image_is_persistent_and_admin_only(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "ci-secret")
    monkeypatch.setenv("SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("COOKIE_SECURE", "0")
    accounts = [
        {"id": 1, "display_name": "Administrador", "is_admin": True, "is_active": True,
         "password_hash": security.hash_password("senha-admin-test-123")},
        {"id": 2, "display_name": "Leitor", "is_admin": False, "is_active": True,
         "password_hash": security.hash_password("senha-leitor-test-123")},
    ]
    asset = {}

    def select(kind, *, fields="*", order=None, params=None):
        if kind == "users":
            rows = accounts
            if params and "id" in params:
                rows = [r for r in rows if int(r["id"]) == int(params["id"].removeprefix("eq."))]
        elif kind == "branding":
            rows = [asset] if asset else []
        else:
            rows = []
        return [{k: v for k, v in row.items() if fields == "*" or k in fields.split(",")} for row in rows]

    def call(method, table, *, params=None, data=None, prefer=None):
        assert table == "finance_brand_assets"
        if method == "POST":
            asset.update(data)
            return [dict(asset)]
        if method == "DELETE":
            asset.clear()
            return []
        raise AssertionError(method)

    monkeypatch.setattr(db, "select", select)
    monkeypatch.setattr(db, "call", call)
    monkeypatch.setattr(security, "accounts", lambda: accounts)

    with TestClient(app) as client:
        assert client.get("/api/branding/institutional").json()["has_logo"] is False
        assert client.post("/api/branding/institutional",files={"file":("logo.png",sample_image(),"image/png")}).status_code==401
        assert client.post("/api/login",json={"password":"senha-leitor-test-123"}).status_code==200
        reader=client.get("/api/me").json()
        denied=client.post("/api/branding/institutional",headers={"X-CSRF-Token":reader["csrf"]},files={"file":("logo.png",sample_image(),"image/png")})
        assert denied.status_code==403

        assert client.post("/api/logout",headers={"X-CSRF-Token":reader["csrf"]}).status_code==200
        assert client.post("/api/login",json={"password":"senha-admin-test-123"}).status_code==200
        csrf={"X-CSRF-Token":client.get("/api/me").json()["csrf"]}
        assert client.post("/api/branding/institutional",files={"file":("logo.png",sample_image(),"image/png")}).status_code==403
        wrong=client.post("/api/branding/institutional",headers=csrf,files={"file":("bad.txt",b"not-image","text/plain")})
        assert wrong.status_code==422
        large=client.post("/api/branding/institutional",headers=csrf,files={"file":("large.png",b"x"*(5*1024*1024+1),"image/png")})
        assert large.status_code==413

        saved=client.post("/api/branding/institutional",headers=csrf,files={"file":("logo.png",sample_image(),"image/png")})
        assert saved.status_code==200,saved.text
        assert saved.json()["has_logo"] is True
        assert client.get("/api/branding/institutional").json()["has_logo"] is True
        public_image=client.get("/api/branding/institutional/image")
        assert public_image.status_code==200
        assert public_image.headers["content-type"].startswith("image/webp")
        assert public_image.content[:4]==b"RIFF"
        with Image.open(io.BytesIO(public_image.content)) as img:
            assert img.mode=="RGBA"
            assert img.width < 650
            assert img.height < 200
            assert img.width >= 485
            assert img.height >= 100

        # Leitura de uma imagem LEGADA que foi salva antes do recorte de margens.
        image = Image.open(io.BytesIO(sample_image()))
        old_file = io.BytesIO()
        image.save(old_file, format="WEBP", lossless=True)
        asset["image_data_uri"] = "data:image/webp;base64," + base64.b64encode(old_file.getvalue()).decode()
        old_public = client.get("/api/branding/institutional/image")
        assert old_public.status_code == 200
        with Image.open(io.BytesIO(old_public.content)) as legacy:
            assert legacy.width < 650 and legacy.height < 200

        assert client.delete("/api/branding/institutional",headers=csrf).status_code==200
        assert client.get("/api/branding/institutional").json()["has_logo"] is False
        assert client.get("/api/branding/institutional/image").status_code==404


def test_only_one_source_serves_login_and_footer():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1] / "static"
    html=(root/"index.html").read_text(encoding="utf-8")
    js=(root/"app.js").read_text(encoding="utf-8")
    assert html.count('data-institutional-logo') == 2
    assert html.count('data-institutional-fallback') == 2
    assert "data-action=\"upload-institutional-logo\"" in js
    assert "data-action=\"delete-institutional-logo\"" in js
    assert "applyInstitutionalBrand()" in js
    assert "/api/branding/institutional/image?v=" in js

def test_white_margin_background_is_cropped_without_distorting_logo():
    # Alguns PNGs tem bordas brancas opacas em vez de transparencia.
    opaque = Image.new("RGB", (1200, 600), "white")
    for x in range(300, 905):
        for y in range(240, 351):
            opaque.putpixel((x, y), (22, 45, 72))
    cleaned = branding.trim_logo_margins(opaque)
    assert cleaned.width < 760
    assert cleaned.height < 170
    assert cleaned.width > 600
    assert cleaned.height > 110


def test_existing_compact_brand_image_does_not_expand_or_distort():
    original = Image.new("RGBA", (200, 40), (40, 100, 120, 255))
    cleaned = branding.trim_logo_margins(original)
    assert cleaned.size == original.size
    assert cleaned.getpixel((0, 0)) == original.getpixel((0, 0))


def test_institutional_size_css_covers_desktop_and_mobile():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "static"
    html = (root / "index.html").read_text(encoding="utf-8")
    css = (root / "identity.css").read_text(encoding="utf-8")
    assert "institutional-logo-size-v2" in html
    assert "#login .nexon-lockup img[data-institutional-logo]" in css
    assert ".nexon-app-footer img[data-institutional-logo]" in css
    assert "width:min(265px,100%)" in css
    assert "height:76px" in css
