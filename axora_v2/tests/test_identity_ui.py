"""Verificações da identidade AXORA A Núcleo e dos assets de interface."""
from pathlib import Path
from xml.etree import ElementTree

STATIC = Path(__file__).resolve().parents[1] / "static"


def test_official_identity_assets_are_valid_svg():
    for name in ("axora-mark.svg", "axora-logo.svg", "axora-network.svg"):
        root = ElementTree.fromstring((STATIC / name).read_text(encoding="utf-8"))
        assert root.tag.endswith("svg")
        assert root.attrib.get("viewBox")
    mark = (STATIC / "axora-mark.svg").read_text(encoding="utf-8")
    assert "0B1E3B" in mark
    assert "circle" in mark


def test_approved_login_card_and_branding_are_present():
    page = (STATIC / "index.html").read_text(encoding="utf-8")
    assert page.index("styles.css") < page.index("premium.css") < page.index("identity.css")
    assert 'class="login-card"' in page
    assert 'class="login-brand"' in page
    assert "Organize o presente." in page
    assert "Decida o futuro." in page
    assert 'rel="icon" type="image/svg+xml"' in page
    assert "/assets/axora-mark.svg" in page
    assert "/assets/axora-network.svg" in (STATIC / "identity.css").read_text(encoding="utf-8")
    assert 'id="login-form"' in page
    assert 'id="login-password"' in page


def test_shell_and_mobile_keep_same_identity_and_semantics():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    css = (STATIC / "identity.css").read_text(encoding="utf-8")
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert 'id="sidebar"' in html
    assert 'class="sidebar-brand-mark"' in html
    assert 'id="sidebar-overlay"' in html
    assert "Manrope" in css
    assert "@media(max-width:850px)" in css
    assert "@media(max-width:680px)" in css
    assert "metricIcons" in js
    assert "aria-current" in js
    assert 'document.body.classList.add("menu-open")' in js
