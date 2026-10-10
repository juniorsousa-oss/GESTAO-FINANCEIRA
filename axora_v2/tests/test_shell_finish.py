"""Regressões AXORA: logotipo colapsado, moldura sem sangramento e login compacto."""
from pathlib import Path

BASE=Path(__file__).resolve().parents[1]/"static"


def test_cascade_last_and_old_login_still_present():
    html=(BASE/"index.html").read_text(encoding="utf-8")
    assert html.index("brand-kit.css") < html.index("shell-finish.css")
    assert "brand-icon-atmosphere-r1" in html
    for id_ in ('id="login-password"','id="login-form"','id="toggle-password"','id="sidebar-overlay"'):
        assert id_ in html


def test_desktop_scroll_is_inside_rounded_shell():
    css=(BASE/"shell-finish.css").read_text(encoding="utf-8")
    assert "@media (min-width:851px)" in css
    assert "body:has(#workspace:not(.hidden))" in css
    assert "#workspace.workspace:not(.hidden)" in css
    assert "height:100dvh" in css
    assert "max-height:100dvh" in css
    assert "#workspace .app-column" in css
    assert "overflow:hidden" in css
    assert "#workspace .main-area" in css
    assert "overflow-y:auto" in css
    assert "overscroll-behavior:contain" in css
    assert "#workspace .topbar" in css
    assert "position:relative" in css
    assert "border-radius:0 25px 25px 0" in css


def test_collapsed_sidebar_uses_square_icon():
    html=(BASE/"index.html").read_text(encoding="utf-8")
    css=(BASE/"shell-finish.css").read_text(encoding="utf-8")
    js=(BASE/"brand-kit.js").read_text(encoding="utf-8")
    assert 'id="axora-collapsed-icon"' in html
    assert "src=\"/api/brand-kit/square-icon?prefer=icon\"" in html
    assert "#workspace.sidebar-collapsed #sidebar #axora-collapsed-icon" in css
    assert "#workspace.sidebar-collapsed #sidebar .side-brand>#axora-sidebar-logo" in css
    assert "display:none!important" in css
    assert "object-fit:contain" in css
    assert "/api/brand-kit/square-icon?prefer=icon" in js
    assert "/api/brand-kit/square-icon?prefer=favicon" in js
    assert 'collapsed.src=appHref' in js
    assert 'id="axora-sidebar-logo"' in html


def test_login_is_smaller_balanced_and_right_field_centered():
    css=(BASE/"shell-finish.css").read_text(encoding="utf-8")
    assert "@media (min-width:901px)" in css
    assert "width:min(960px,calc(100vw - 56px))" in css
    assert "height:min(550px,calc(100dvh - 50px))" in css
    assert "#login .login-panel" in css
    assert "align-items:center" in css
    assert "justify-content:center" in css
    assert "max-width:355px" in css
    assert "#login .login-form" in css
    assert "#login .custom-login-logo" in css
    assert "@media (min-width:901px) and (max-height:630px)" in css


def test_mobile_drawer_remains_visible():
    css=(BASE/"shell-finish.css").read_text(encoding="utf-8")
    mobile=(BASE/"mobile-premium.css").read_text(encoding="utf-8")
    assert "@media(max-width:850px)" in css
    assert "#sidebar #axora-collapsed-icon {display:none!important;}" in css
    assert "#sidebar-overlay.sidebar-overlay.open" in mobile
    assert "z-index:81" in mobile
