"""Contrato de acabamento Nexon compartilhado em todas as telas AXORA."""
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "static"


def test_new_design_layer_loads_after_approved_login_without_overriding_it():
    html = (BASE / "index.html").read_text(encoding="utf-8")
    css = (BASE / "refinement.css").read_text(encoding="utf-8")
    assert html.index("finish.css") < html.index("login-fidelity.css") < html.index("refinement.css")
    assert 'design-system-r1' in html
    assert '#login.login-screen' not in css
    assert '#login .login-card' not in css
    assert '#login .login-art' not in css


def test_header_status_and_breadcrumb_are_semantic_and_actionable():
    html = (BASE / "index.html").read_text(encoding="utf-8")
    js = (BASE / "app.js").read_text(encoding="utf-8")
    assert 'aria-label="Localização atual"' in html
    assert 'class="crumb-brand"' in html
    assert 'id="crumb-current"' in html
    for label in ("top-sync-status", "sidebar-sync-status", "sidebar-sync-time", "refresh"):
        assert 'id="' + label + '"' in html
    assert 'data-state="loading"' in html
    assert 'aria-live="polite"' in html
    assert 'id="profile-button"' in html
    assert 'updateSyncStatus("loading")' in js
    assert 'updateSyncStatus("ready")' in js
    assert 'updateSyncStatus("error")' in js
    assert 'snapshot=latest' in js
    assert 'button.disabled=false' in js
    assert "Plataforma conectada" not in html


def test_common_iconography_and_actions_cover_all_modules():
    js = (BASE / "app.js").read_text(encoding="utf-8")
    css = (BASE / "refinement.css").read_text(encoding="utf-8")
    for icon in ('plus:', 'download:', 'edit:', 'trash:', 'reset:'):
        assert icon in js
    assert 'class="ui-icon"' in js
    for action in ('data-action="export"', 'data-action="new-movement"',
                   'data-action="new"', 'data-action="edit"',
                   'data-action="delete"', 'data-action="clear-filters"',
                   'data-action="preview-import"', 'data-action="commit-import"'):
        assert action in js
    assert '.ui-icon' in css
    assert '.mini-btn .ui-icon' in css
    assert '.btn.primary' in css
    assert '.page-heading' in css
    assert '.filters' in css
    assert '.data-table' in css
    assert '.settings-form' in css
    assert '.editor-dialog' in css


def test_mobile_controls_keep_menu_and_sync_accessible():
    html = (BASE / "index.html").read_text(encoding="utf-8")
    css = (BASE / "refinement.css").read_text(encoding="utf-8")
    assert 'id="menu-toggle"' in html
    assert 'id="close-menu"' in html
    assert 'id="sidebar-overlay"' in html
    assert '@media(max-width:850px)' in css
    assert '@media(max-width:680px)' in css
    assert '@media(max-width:375px)' in css
    assert '#top-sync-status{display:inline-flex' in css
    assert 'prefers-reduced-motion:reduce' in css


def test_brand_fonts_and_proportional_palette_remain_consistent():
    css = (BASE / "refinement.css").read_text(encoding="utf-8")
    assert "font-family:Manrope,Inter,sans-serif" in css
    assert "font-family:Inter,sans-serif" in css
    assert '--ax-ink:#102B49' in css
    assert '--ax-cta:#0BAFA8' in css
    assert '.metric-card,.panel' in css
    assert '.donut-legend-line' in css
    assert '.toast' in css
