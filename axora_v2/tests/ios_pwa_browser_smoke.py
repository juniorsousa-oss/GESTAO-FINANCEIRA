"""Geometria real no Chrome mobile — detecta saltos ao abrir teclado e chanfro inferior.

Executar com APP_URL=http://127.0.0.1:18081, no GitHub Actions.
Emulação de teclado reduz o viewport mas não tenta simular a status bar iOS,
que precisa de teste estático e validação final no dispositivo.
"""
import os
import shutil

from playwright.sync_api import sync_playwright

URL = os.environ.get("AXORA_SMOKE_URL", "http://127.0.0.1:18081/")
CHROME = next((shutil.which(cmd) for cmd in ("google-chrome", "chromium", "chromium-browser")
               if shutil.which(cmd)), None)
if not CHROME:
    raise RuntimeError("Chrome/Chromium não encontrado no runner de validação.")

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox"])
    context = browser.new_context(viewport={"width": 390, "height": 844},
                                  device_scale_factor=3, is_mobile=True, has_touch=True)
    page = context.new_page()
    page.goto(URL, wait_until="domcontentloaded")
    page.locator("#login .login-card").wait_for()
    start = page.locator("#login .login-card").bounding_box()
    assert start is not None and start["width"] < 390
    assert start["height"] > 350
    body_color = page.locator("body").evaluate(
        "(node) => getComputedStyle(node).backgroundColor")
    assert body_color in ("rgb(6, 44, 69)", "rgba(6, 44, 69, 1)"), body_color

    page.locator("#login-password").focus()
    page.set_viewport_size({"width":390,"height":495})
    page.wait_for_timeout(150)
    with_keyboard = page.locator("#login .login-card").bounding_box()
    assert with_keyboard is not None
    assert abs(start["y"] - with_keyboard["y"]) <= 2, (start, with_keyboard)
    assert abs(start["height"] - with_keyboard["height"]) <= 2, (start, with_keyboard)
    locked=page.evaluate("getComputedStyle(document.querySelector('#login')).height")
    assert locked.endswith("px") and float(locked[:-2]) >= 800, locked

    page.set_viewport_size({"width":390,"height":844})
    page.locator("#login-password").blur()
    page.evaluate("""() => {
      document.querySelector('#login').classList.add('hidden');
      document.querySelector('#workspace').classList.remove('hidden');
    }""")
    page.wait_for_timeout(120)
    shell = page.locator("#workspace .app-column")
    rect = shell.bounding_box()
    assert rect is not None
    # A moldura deve TERMINAR antes da borda inferior, com canto arredondado.
    shell_bottom = rect["y"] + rect["height"]
    assert 8 <= 844 - shell_bottom <= 60, (rect, shell_bottom)
    radius = shell.evaluate("(el)=>getComputedStyle(el).borderBottomLeftRadius")
    assert radius.endswith("px") and float(radius[:-2]) >= 18, radius
    main = page.locator("#workspace .main-area")
    assert main.evaluate("(el)=>getComputedStyle(el).overflowY") == "auto"
    assert page.locator("#workspace .topbar").is_visible()

    # Conteúdo curto: nenhum espaço branco grande após a assinatura.
    page.locator("#page-content").evaluate("(el)=>el.replaceChildren()")
    page.locator(".page-heading").evaluate("(el)=>el.style.display='none'")
    page.wait_for_timeout(100)
    viewport = main.bounding_box()
    foot = page.locator("#workspace .app-footer").bounding_box()
    assert viewport and foot
    short_gap = viewport["y"] + viewport["height"] - (foot["y"] + foot["height"])
    assert 8 <= short_gap <= 45, ("footer gap", short_gap, viewport, foot)

    # Conteúdo longo: somente o painel interno rola e o rodapé continua
    # depois do último cartão, sem lacuna artificial no final do scroll.
    page.locator("#page-content").evaluate("""(container)=>{
      for(let i=0;i<24;i++){
        const item=document.createElement("div");
        item.className="panel";
        item.textContent="Conteúdo financeiro de teste "+i;
        item.style.minHeight="130px";
        item.style.marginBottom="15px";
        container.append(item);
      }
    }""")
    page.wait_for_timeout(80)
    lengths=main.evaluate("(el)=>[el.scrollHeight,el.clientHeight]")
    assert lengths[0] > lengths[1] + 1000, lengths
    main.evaluate("(el)=>{el.scrollTop=el.scrollHeight;}")
    page.wait_for_timeout(100)
    last_foot = page.locator("#workspace .app-footer").bounding_box()
    last_view = main.bounding_box()
    assert last_foot and last_view
    long_gap = last_view["y"] + last_view["height"] - (last_foot["y"] + last_foot["height"])
    assert 8 <= long_gap <= 45, ("long footer gap", long_gap, last_view, last_foot)
    assert abs(shell.bounding_box()["y"] + shell.bounding_box()["height"] - shell_bottom) <= 2
    print("AXORA iPhone viewport + rodapé curto/longo: OK")
    browser.close()
