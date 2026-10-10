"""AXORA mobile: login integrado tipo Opera/ATRIA e fundo fora do frame."""
from pathlib import Path

STATIC=Path(__file__).resolve().parents[1]/"static"


def test_layer_loaded_after_every_prior_design_override():
    html=(STATIC/"index.html").read_text(encoding="utf-8")
    assert html.index("login-fidelity.css") < html.index("mobile-premium.css")
    assert html.index("mobile-premium.css") < html.index("shell-finish.css")
    assert html.index("shell-finish.css") < html.index("mobile-frame-login-v2.css")
    assert "opera-atria-card-mobile-r1" in html


def test_mobile_background_is_external_and_interior_keeps_finance_colors():
    css=(STATIC/"mobile-frame-login-v2.css").read_text(encoding="utf-8")
    assert "@media (max-width:850px)" in css
    assert 'body:has(#workspace:not(.hidden))' in css
    assert 'background-image:url("/assets/login-atmosphere.svg")' in css
    assert "#workspace.workspace:not(.hidden)" in css
    assert "background:transparent" in css
    assert "#workspace.workspace:not(.hidden) .app-column" in css
    assert "background:linear-gradient(156deg,#F9FCFE" in css
    assert "padding:var(--ax-mobile-gutter)" in css
    assert "border-radius:var(--ax-mobile-radius)" in css
    assert "#workspace .topbar" in css
    assert "border-radius:calc(var(--ax-mobile-radius) - 1px)" in css


def test_login_uses_single_rounded_card_not_overlapping_sheets():
    css=(STATIC/"mobile-frame-login-v2.css").read_text(encoding="utf-8")
    assert "@media (max-width:900px)" in css
    assert "#login.login-screen" in css
    assert "justify-content:center" in css
    assert "#login .login-card" in css
    assert "width:min(476px,100%)" in css
    assert "flex-direction:column" in css
    assert "overflow:hidden" in css
    assert "border-radius:27px" in css
    assert "#login .login-panel" in css
    assert "margin:0" in css
    assert "border-radius:0" in css
    assert "box-shadow:none" in css
    assert "width:100%" in css
    assert "#login .login-art" in css
    assert 'url("/assets/login-hero-network.svg")' in css


def test_login_fields_and_logo_are_accessible_at_all_mobile_sizes():
    css=(STATIC/"mobile-frame-login-v2.css").read_text(encoding="utf-8")
    html=(STATIC/"index.html").read_text(encoding="utf-8")
    for sel in ("#login .custom-login-logo","#login .login-form-wrap",
                "#login .password-wrap","#login .password-wrap input",
                "#login .login-form .btn","#login .login-foot.nexon-lockup",
                "#login .nexon-lockup img[data-institutional-logo]"):
        assert sel in css
    assert "font-size:16px" in css
    assert "@media (max-width:600px)" in css
    assert "@media(max-width:390px)" in css
    assert "@media(max-width:900px) and (max-height:660px)" in css
    assert "env(safe-area-inset-bottom,0px)" in css
    assert 'id="login-password"' in html
    assert 'id="login-form"' in html
    assert "data-institutional-logo" in html
