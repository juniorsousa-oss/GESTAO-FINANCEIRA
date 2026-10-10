"""Contrato visual para login AXORA validado (card 1140x685, proporções e mobile)."""
from pathlib import Path
from xml.etree import ElementTree

BASE = Path(__file__).resolve().parents[1] / "static"


def test_login_fidelity_styles_are_loaded_last():
    html = (BASE / "index.html").read_text(encoding="utf-8")
    assert html.index("styles.css") < html.index("premium.css")
    assert html.index("premium.css") < html.index("identity.css")
    assert html.index("identity.css") < html.index("finish.css")
    assert html.index("finish.css") < html.index("login-fidelity.css")
    assert "approved-image-1" in html


def test_login_has_approved_headline_and_copy_without_altering_actions():
    html = (BASE / "index.html").read_text(encoding="utf-8")
    assert '<span class="hero-line">Seu futuro</span>' in html
    assert '<span class="hero-line">financeiro merece</span>' in html
    assert '<em class="hero-line">clareza.</em>' in html
    assert '<span>Transforme números em decisões.</span>' in html
    assert '<span>Organize, acompanhe e evolua</span>' in html
    assert '<div class="login-pill">Da informação à decisão.</div>' in html
    # A frase institucional longa fica no rodapé interno, não na tela de login.
    assert 'AXORA · Organize o presente. Decida o futuro.' in html
    assert 'id="login-form"' in html
    assert 'id="login-password"' in html
    assert 'id="toggle-password"' in html
    assert html.count("data-institutional-logo") == 2
    assert "nexon-monochrome-dark.svg" not in html


def test_exact_visual_dimensions_and_background_assets():
    css = (BASE / "login-fidelity.css").read_text(encoding="utf-8")
    assert "width:min(1140px,100%)" in css
    assert "height:min(685px,calc(100dvh - 75px))" in css
    assert "grid-template-columns:minmax(0,1fr) minmax(0,1fr)" in css
    assert "url(\"/assets/login-atmosphere.svg\")" in css
    assert "url(\"/assets/login-hero-network.svg\")" in css
    assert "font-family:Manrope,Inter,sans-serif" in css
    assert "font-family:Inter,sans-serif" in css
    assert "font-size:40px" in css
    assert "font-size:16px" in css
    assert "width:154px" in css
    assert "filter:grayscale(1)" in css


def test_login_tech_backgrounds_are_valid_standalone_svg():
    for name in ("login-atmosphere.svg", "login-hero-network.svg"):
        doc = ElementTree.fromstring((BASE / name).read_text(encoding="utf-8"))
        assert doc.tag.endswith("svg")
        assert doc.attrib["viewBox"]
        paths = list(doc.iter("{http://www.w3.org/2000/svg}path"))
        assert len(paths) >= 3
        assert any("filter" in element.attrib for element in doc.iter())


def test_mobile_and_compact_desktop_remain_accessible():
    css = (BASE / "login-fidelity.css").read_text(encoding="utf-8")
    for breakpoint in (
        "@media(min-width:901px) and (max-width:1200px)",
        "@media(min-width:901px) and (max-height:755px)",
        "@media(max-width:900px)",
        "@media(max-width:480px)",
        "@media(prefers-reduced-motion:reduce)",
    ):
        assert breakpoint in css
    assert "min-height:66px" in css
    assert "min-height:53px" in css
    assert "#login [hidden] {display:none!important;}" in css


def test_login_footer_matches_atria_desktop_and_preserves_mobile():
    html = (BASE / "index.html").read_text(encoding="utf-8")
    css = (BASE / "shell-finish.css").read_text(encoding="utf-8")
    mobile = (BASE / "mobile-frame-login-v2.css").read_text(encoding="utf-8")
    assert "exterior-network-wallpaper-r2-login-foot-v1" in html
    assert "Rodapé do painel esquerdo no padrão ATRIA" in css
    assert "#login .login-art-content {\n    height:100%;" in css
    assert "margin:auto 0 0" in css
    assert "width:50px;" in css
    assert "linear-gradient(90deg,#34E0CF,#28B8D6)" in css
    assert "#login .login-pill{display:none;}" in mobile
