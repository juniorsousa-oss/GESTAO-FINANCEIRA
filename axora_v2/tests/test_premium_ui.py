"""Checagens de regressao para a camada visual AXORA Premium."""
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / "static"


def test_premium_theme_is_loaded_after_base():
    html = (ASSETS / "index.html").read_text(encoding="utf-8")
    assert html.index("/assets/styles.css") < html.index("/assets/premium.css")
    assert 'name="viewport"' in html
    assert 'aria-controls="sidebar"' in html
    assert 'id="login-form"' in html


def test_premium_theme_has_desktop_and_mobile_shells():
    css = (ASSETS / "premium.css").read_text(encoding="utf-8")
    assert ".workspace.sidebar-collapsed" in css
    assert ".login-screen" in css
    assert ".metric-card" in css
    assert "@media(max-width:850px)" in css
    assert "@media(max-width:680px)" in css
    assert ".data-table td::before" in css
    assert "prefers-reduced-motion" in css


def test_responsive_tables_and_navigation_are_wired():
    js = (ASSETS / "app.js").read_text(encoding="utf-8")
    assert 'data-label="' in js  # headers must be supplied for mobile rows
    assert "displayTableCell(cell,headings[j])" in js
    assert 'document.body.classList.add("menu-open")' in js
    assert 'document.body.classList.remove("menu-open")' in js
    assert 'syncMenuTrigger()' in js
