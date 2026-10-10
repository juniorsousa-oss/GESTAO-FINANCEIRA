"""AXORA: branding sem flash, ícones quadrados e atmosfera na interface."""
import io
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from axora_v2 import branding, db
from axora_v2.main import app

ROOT=Path(__file__).resolve().parents[1]/"static"


def png(width, height):
    image=Image.new("RGBA",(width,height),(0,0,0,0))
    fill=Image.new("RGBA",(int(width*.8),int(height*.8)),(12,69,91,255))
    image.alpha_composite(fill,(width//10,height//10))
    buf=io.BytesIO()
    image.save(buf,"PNG")
    return buf.getvalue()


def test_square_icon_keeps_content_and_exact_dimensions():
    mime,uri=branding.prepare_logo(png(420,420),"image/png")
    assert mime=="image/webp"
    out=branding.render_square_icon(uri,256)
    with Image.open(io.BytesIO(out)) as im:
        assert im.size==(256,256)
        assert im.mode=="RGBA"
        assert im.getpixel((0,0))[3]==0
        assert im.getpixel((128,128))[3]>0
        bbox=im.getchannel("A").getbbox()
        assert bbox is not None and bbox[2]-bbox[0]>=248
        assert bbox[3]-bbox[1]>=248


def test_reject_new_horizontal_logos_as_icons():
    branding.validate_square_upload(png(420,420))
    with pytest.raises(HTTPException) as exc:
        branding.validate_square_upload(png(900,230))
    assert exc.value.status_code==422
    mime,uri=branding.prepare_logo(png(900,230),"image/png")
    assert mime=="image/webp"
    with pytest.raises(HTTPException) as exc:
        branding.render_square_icon(uri)
    assert exc.value.status_code==422


def test_browser_favicon_route_fallback_and_priority(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "ci-only")
    monkeypatch.setenv("SESSION_SECRET", "long-ci-secret-just-for-fastapi-tests-20261010")
    correct=branding.prepare_logo(png(300,300),"image/png")[1]
    wrong=branding.prepare_logo(png(900,230),"image/png")[1]
    def fake_select(kind,*,fields="*",order=None,params=None):
        assert kind=="branding"
        return [{"key":"axora_favicon","image_data_uri":wrong},
                {"key":"axora_icon","image_data_uri":correct}]
    monkeypatch.setattr(db,"select",fake_select)
    with TestClient(app) as client:
        fav=client.get("/api/brand-kit/square-icon?prefer=favicon")
        appicon=client.get("/api/brand-kit/square-icon?prefer=icon")
        for result in (fav,appicon):
            assert result.status_code==200
            assert result.headers["content-type"].startswith("image/png")
            with Image.open(io.BytesIO(result.content)) as im:
                assert im.size==(256,256)
        assert client.get("/api/brand-kit/square-icon?prefer=invalid").status_code==422
    monkeypatch.setattr(db,"select",lambda *args,**kwargs: [])
    with TestClient(app) as client:
        default=client.get("/api/brand-kit/square-icon")
        assert default.status_code==200
        assert default.headers["content-type"].startswith("image/svg+xml")


def test_no_fallback_flash_and_atmosphere_is_reused():
    html=(ROOT/"index.html").read_text()
    kit=(ROOT/"brand-kit.js").read_text()
    css=(ROOT/"shell-finish.css").read_text()
    assert 'class="login-art-content brand-pending"' in html
    assert 'class="side-brand brand-pending"' in html
    assert "container.classList.remove(\"brand-pending\")" in kit
    assert "#login .login-art-content.brand-pending>.login-brand" in css
    assert "#sidebar .side-brand.brand-pending" in css
    assert 'href="/api/brand-kit/square-icon?prefer=favicon&rev=brandframe-v2"' in html
    assert 'id="axora-collapsed-icon"' in html
    assert "/assets/login-atmosphere.svg" in css
    assert "body:has(#workspace:not(.hidden))" in css
    assert "background-attachment:fixed" in css
    assert 'background-image:url("/assets/login-atmosphere.svg")' in css
    assert "background:linear-gradient(145deg,#F9FCFE" in css
    assert "brand-icon-flash-r1" in html
