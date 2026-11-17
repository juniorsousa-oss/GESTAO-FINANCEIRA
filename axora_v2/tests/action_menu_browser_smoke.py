"""Teste visual e funcional dos menus de ações usando Chromium real.

Impede cards de crescer ao abrir o popover e cobre clique fora, ação,
tecla Escape, exclusividade, seleção de campos e diferentes viewports.
"""
import os
import shutil
from playwright.sync_api import sync_playwright

URL=os.environ.get("AXORA_SMOKE_URL","http://127.0.0.1:18081/")
CHROME=next((shutil.which(name) for name in
             ("google-chrome","chromium","chromium-browser") if shutil.which(name)),None)
assert CHROME,"Chromium não encontrado"

BANK_FIXTURE="""
<div id="smoke-fixture" style="position:fixed;top:54px;left:12px;
 width:min(760px,calc(100vw - 24px));z-index:20000;background:white;padding:8px">
<details class="bank-person-card" open>
 <summary class="bank-person-summary"><strong>Principal</strong></summary>
 <div class="bank-person-detail" style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr))">
  {}
 </div>
</details></div>
"""
BANK_CARD="""
<article id="b{}" class="bank-account-card bank-person-account">
<div class="bank-card-top">
 <span class="bank-icon">B</span><span class="bank-tag">Manual</span>
 <details class="bank-account-menu axora-action-menu">
  <summary aria-expanded="false" title="Ações">⋮</summary>
  <div class="bank-account-menu-panel axora-action-menu-panel">
   <button type="button" class="btn ghost small" data-action="test-action">Editar</button>
   <button type="button" class="btn ghost small" data-action="test-action">Transferir</button>
   <button type="button" class="btn ghost small" data-action="test-action">Atualizar</button>
  </div>
 </details>
</div>
<strong class="bank-account-name">Banco {}</strong>
<div class="bank-manual-balance"><span>Disponível</span><strong>R$ 100,00</strong></div>
</article>
"""
FAMILY_FIXTURE="""
<div id="smoke-fixture" style="position:fixed;top:54px;left:12px;
 width:min(500px,calc(100vw - 24px));z-index:20000;background:white;padding:8px">
<article id="family-card" class="family-person-summary">
<div class="family-person-heading">
 <div class="family-avatar">B</div>
 <div class="family-person-identity"><strong>Bianca</strong><small>Cônjuge</small></div>
 <details class="family-member-menu axora-action-menu">
  <summary aria-expanded="false" title="Ações">⋮</summary>
  <div class="family-member-menu-panel axora-action-menu-panel">
   <label for="role-choice">Vínculo</label>
   <select id="role-choice"><option value="conjuge">Cônjuge</option>
      <option value="pai">Pai</option></select>
   <button class="btn ghost" type="button" data-family-action="test-family-action">Salvar</button>
  </div>
 </details>
</div>
<div class="family-person-metrics"><div><span>Entradas</span><b>R$ 0,00</b></div>
  <div><span>Saídas</span><b>R$ 0,00</b></div></div>
</article></div>
"""

with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=CHROME,headless=True,args=["--no-sandbox"])
    for width,height in [(1366,768),(390,844)]:
        context=browser.new_context(viewport={"width":width,"height":height},
                                    is_mobile=width<500,has_touch=width<500)
        page=context.new_page()
        page.goto(URL,wait_until="networkidle")
        assert page.evaluate("typeof window.AxoraActionMenus")== "object"

        page.evaluate("""(markup)=>{
          document.body.insertAdjacentHTML('beforeend',markup);
          window.__smokeActions=0;
          document.addEventListener('click',e=>{
            if(e.target.matches('[data-action="test-action"],[data-family-action="test-family-action"]'))
              window.__smokeActions++;
          });
        }""",BANK_FIXTURE.format(BANK_CARD.format(1,1),BANK_CARD.format(2,2)))
        a,b=page.locator("#b1"),page.locator("#b2")
        size=lambda el:(el.bounding_box()["width"],el.bounding_box()["height"])
        before=(size(a),size(b))
        a.locator("summary").click()
        page.wait_for_function("document.querySelector('#b1 details.bank-account-menu').open")
        assert size(a)==before[0] and size(b)==before[1],("Menu alterou card",width,before,size(a),size(b))
        panel=a.locator(".bank-account-menu-panel")
        rect=panel.bounding_box()
        assert rect and rect["x"]>=8 and rect["x"]+rect["width"]<=width+1,(width,rect)
        assert rect["y"]>=0 and rect["y"]+rect["height"]<=height+1,(width,rect)
        assert panel.evaluate("""el=>{
          let r=el.getBoundingClientRect(),hit=document.elementFromPoint(r.left+12,r.top+12);
          return el===hit||el.contains(hit);
        }"""),"Popover coberto por outro card"
        assert a.locator("summary").get_attribute("aria-expanded")=="true"

        b.locator("summary").click()
        assert not a.locator("details.bank-account-menu").evaluate("(e)=>e.open")
        assert b.locator("details.bank-account-menu").evaluate("(e)=>e.open")
        assert size(a)==before[0] and size(b)==before[1]
        page.mouse.click(5,5)
        assert not b.locator("details.bank-account-menu").evaluate("(e)=>e.open"),"Clique fora não fechou"
        b.locator("summary").click()
        page.keyboard.press("Escape")
        assert not b.locator("details.bank-account-menu").evaluate("(e)=>e.open"),"Escape não fechou"
        b.locator("summary").click()
        b.locator('[data-action="test-action"]').first.click()
        page.wait_for_function("window.__smokeActions===1")
        page.wait_for_function("!document.querySelector('details.bank-account-menu[open]')")
        assert size(a)==before[0] and size(b)==before[1]
        assert page.locator("details.bank-person-card[open]").count()==1,"Acordeão de titular foi fechado"

        page.locator("#smoke-fixture").evaluate("(node)=>node.remove()")
        page.evaluate("(markup)=>document.body.insertAdjacentHTML('beforeend',markup)",FAMILY_FIXTURE)
        family=page.locator("#family-card")
        original=size(family)
        family.locator("summary").click()
        assert size(family)==original,"Menu familiar redimensionou card"
        family.locator("select").select_option("pai")
        assert family.locator("details.family-member-menu").evaluate("(e)=>e.open"),"Editar vínculo fechou menu"
        family.locator('[data-family-action="test-family-action"]').click()
        page.wait_for_function("window.__smokeActions===2")
        page.wait_for_function("!document.querySelector('details.family-member-menu[open]')")
        assert size(family)==original
        print(f"AXORA: menus de ações verificados em {width}x{height}")
        context.close()
    browser.close()
