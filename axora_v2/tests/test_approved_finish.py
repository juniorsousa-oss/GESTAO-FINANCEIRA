"""Regressão estática do acabamento AXORA aprovado no mockup de login."""
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "static"


def test_validated_design_layer_loads_last():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert html.index("styles.css") < html.index("premium.css")
    assert html.index("premium.css") < html.index("identity.css")
    assert html.index("identity.css") < html.index("finish.css")
    assert "approved-signature-sidebar-v1" in html
    assert 'id="login-form"' in html
    assert 'id="login-password"' in html
    assert 'id="sidebar"' in html
    assert 'id="main-nav"' in html


def test_nexon_signature_is_discreet_but_shared():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    css = (STATIC / "finish.css").read_text(encoding="utf-8")
    assert html.count('data-institutional-logo') == 2
    assert html.count('data-institutional-fallback') == 2
    assert "#login .nexon-lockup img[data-institutional-logo]" in css
    assert "width:148px" in css
    assert "height:43px" in css
    assert ".nexon-app-footer img[data-institutional-logo]" in css
    assert "width:145px" in css
    assert "grayscale(1)" in css
    assert "/assets/axora-network.svg" in css


def test_premium_sidebar_works_with_collapsed_and_mobile_drawer():
    css = (STATIC / "finish.css").read_text(encoding="utf-8")
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert ".nav-link.active" in css
    assert ".nav-icon svg" in css
    assert ".sidebar-bottom" in css
    assert ".workspace.sidebar-collapsed .sidebar" in css
    assert "@media(max-width:850px)" in css
    assert "@media(max-width:680px)" in css
    assert "prefers-reduced-motion" in css
    assert "menu-open" in js
    assert "syncMenuTrigger()" in js


def test_brand_typography_and_finance_modules_remain_consistent():
    css = (STATIC / "finish.css").read_text(encoding="utf-8")
    identity = (STATIC / "identity.css").read_text(encoding="utf-8")
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "Manrope" in css and "Inter" in css
    assert "#login .login-card" in css
    assert ".metric-card,.panel" in css
    assert ".data-table" in css
    assert "identity.css" in html
    assert "institutional-brand-editor" in identity
