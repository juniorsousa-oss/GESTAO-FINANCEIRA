"""Regressão PWA iPhone: status bar, safe areas, teclado e moldura inferior."""
from pathlib import Path
from html.parser import HTMLParser
import json

STATIC = Path(__file__).resolve().parents[1] / "static"


class HeadParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}
        self.links = []
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        props = dict(attrs)
        if tag == "meta":
            self.meta[props.get("name")] = props.get("content")
        if tag == "link" and props.get("rel") == "stylesheet":
            self.links.append(props.get("href", ""))
        if tag == "script" and props.get("src"):
            self.scripts.append(props["src"])


def _head():
    parser = HeadParser()
    parser.feed((STATIC / "index.html").read_text())
    return parser


def test_fullscreen_iphone_pwa_status_color_matches_manifest():
    head = _head()
    manifest = json.loads((STATIC / "pwa/manifest.json").read_text())
    assert "viewport-fit=cover" in head.meta["viewport"]
    assert head.meta["apple-mobile-web-app-capable"] == "yes"
    assert head.meta["apple-mobile-web-app-status-bar-style"] == "black-translucent"
    assert head.meta["theme-color"] == "#062C45"
    assert manifest["background_color"] == manifest["theme_color"] == "#062C45"
    assert manifest["display"] == "standalone"


def test_final_mobile_layer_runs_after_earlier_styles():
    head = _head()
    assert head.links[-1].startswith("/assets/ios-pwa-finish.css")
    assert any("mobile-scroll-stability.css" in link for link in head.links[:-1])
    assert any("mobile-frame-login-v2.css" in link for link in head.links[:-1])
    assert any("family.css" in link for link in head.links[:-1])
    assert head.scripts[-1].startswith("/assets/ios-pwa-stability.js")
    assert (STATIC / "ios-pwa-finish.css").is_file()
    assert (STATIC / "ios-pwa-stability.js").is_file()


def test_keyboard_does_not_resize_or_recenter_card_when_visual_viewport_shrinks():
    css = (STATIC / "ios-pwa-finish.css").read_text()
    js = (STATIC / "ios-pwa-stability.js").read_text()
    assert "height:var(--axora-login-stage-height,100svh)" in css
    assert "min-height:var(--axora-login-stage-height,100svh)" in css
    assert "justify-content:safe center" in css
    assert "overflow-y:auto" in css
    assert "#login .login-card" in css
    assert "font-size:16px!important" in css
    assert "window.innerHeight" in js
    assert "window.addEventListener(\"resize\"" in js
    assert "Math.abs(width-lastWidth)>2" in js
    assert "document.activeElement?.id" in js


def test_safe_area_and_square_bottom_without_screen_clipping():
    css = (STATIC / "ios-pwa-finish.css").read_text()
    assert "env(safe-area-inset-top,0px)" in css
    assert "env(safe-area-inset-bottom,0px)" in css
    assert "env(safe-area-inset-left,0px)" in css
    assert "env(safe-area-inset-right,0px)" in css
    assert "border-bottom:0" in css
    assert "0 0;" in css
    assert "height:calc(100dvh - var(--axora-mobile-top))" in css
    assert "overflow-y:auto" in css
    assert "#workspace.workspace:not(.hidden) .main-area" in css


def test_original_mobile_screen_and_branding_remain():
    html = (STATIC / "index.html").read_text()
    assert 'id="login-password"' in html
    assert 'id="login-form"' in html
    assert 'id="workspace"' in html
    assert 'id="sidebar"' in html
    assert html.count("data-institutional-logo") == 2
