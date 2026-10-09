"""AXORA mobile Nexon: moldura refinada, conteúdo fluido e drawer acima do overlay."""
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "static"


def test_mobile_layer_is_last_and_scoped():
    html = (BASE / "index.html").read_text(encoding="utf-8")
    css = (BASE / "mobile-premium.css").read_text(encoding="utf-8")
    assert html.index("refinement.css") < html.index("mobile-premium.css")
    assert "nexon-mobile-frame-v1" in html
    assert css.index("@media (max-width:850px)") < css.index("@media (max-width:600px)")
    assert "@media(max-width:390px)" in css
    assert "border-radius:var(--ax-mobile-radius)" in css
    assert "#workspace .app-column" in css
    assert "#workspace .topbar" in css
    assert "#login .login-card" in css
    assert "max-width:100%" in css


def test_overlay_and_drawer_avoid_atria_mobile_stacking_regression():
    css = (BASE / "mobile-premium.css").read_text(encoding="utf-8")
    html = (BASE / "index.html").read_text(encoding="utf-8")
    js = (BASE / "app.js").read_text(encoding="utf-8")
    assert "#sidebar-overlay.sidebar-overlay" in css
    assert "#sidebar.sidebar" in css
    assert "z-index:80" in css and "z-index:81" in css
    assert "pointer-events:auto" in css
    assert "visibility:visible" in css
    assert "isolation:auto" in css
    assert 'id="sidebar-overlay"' in html
    assert 'id="sidebar"' in html
    assert 'id="close-menu"' in html
    assert 'aria-controls="sidebar"' in html
    assert "sidebar.inert=mobile&&!open" in js
    assert 'sidebar.setAttribute("aria-hidden"' in js
    assert "trapMobileMenuFocus(e)" in js
    assert 'e.key==="Escape"' in js
    assert 'document.body.classList.add("menu-open")' in js


def test_mobile_finance_views_have_no_forced_wide_table():
    css = (BASE / "mobile-premium.css").read_text(encoding="utf-8")
    assert "#workspace .metric-grid" in css
    assert "grid-template-columns:minmax(0,1fr)" in css
    assert "#workspace .donut-container" in css
    assert "#workspace .chart-svg" in css
    assert "#workspace .data-table thead{display:none;}" in css
    assert '#workspace .data-table td::before' in css
    assert '#workspace .data-table td[data-label="Ações"]' in css
    assert "#workspace .filters" in css
    assert "#workspace .settings-grid" in css
    assert "#workspace .field.checkbox" in css
    assert "#editor-dialog.editor-dialog" in css
    assert "#workspace .nexon-app-footer" in css


def test_mobile_login_uses_same_signature_and_premium_identity():
    css = (BASE / "mobile-premium.css").read_text(encoding="utf-8")
    html = (BASE / "index.html").read_text(encoding="utf-8")
    assert 'url("/assets/login-atmosphere.svg")' in css
    assert 'url("/assets/login-hero-network.svg")' in css
    assert "#login .login-form" in css
    assert "#login .nexon-lockup img[data-institutional-logo]" in css
    assert html.count("data-institutional-logo") == 2
    assert "prefers-reduced-motion:reduce" in css
    assert 'env(safe-area-inset-bottom,0px)' in css
