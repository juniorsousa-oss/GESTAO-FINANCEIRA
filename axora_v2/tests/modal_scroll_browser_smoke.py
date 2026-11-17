"""Auditoria geométrica de TODOS os modais do AXORA usando Chromium real.

Garante que o trilho de rolagem do desktop fique dentro da moldura arredondada
e que mobile/teclado preservem uma superfície de rolagem utilizável.
"""
import os
import shutil
from playwright.sync_api import sync_playwright

URL=os.environ.get("AXORA_SMOKE_URL","http://127.0.0.1:18081/")
CHROME=next((shutil.which(p) for p in ("google-chrome","chromium","chromium-browser")
             if shutil.which(p)),None)
if not CHROME:
    raise RuntimeError("Chromium não encontrado")

SELECTOR="dialog.editor-dialog,dialog.family-dialog,dialog.bank-dialog,dialog.provision-dialog"

with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=CHROME,headless=True,args=["--no-sandbox"])
    for width,height in ((1440,900),(900,710),(390,844),(820,780)):
        context=browser.new_context(viewport={"width":width,"height":height},
                                    is_mobile=width<=850,has_touch=width<=850)
        page=context.new_page()
        page.goto(URL,wait_until="networkidle")
        ids=page.locator(SELECTOR).evaluate_all("(els)=>els.map(e=>e.id)")
        assert len(ids)>=15,("Modal não coberto pela auditoria",ids)
        for id in ids:
            locator=page.locator("#"+id)
            locator.evaluate("""(dialog)=>{
              const content=dialog.querySelector(':scope > form, :scope > .provision-pix-content');
              if(!content)throw new Error('Modal sem superfície de rolagem '+dialog.id);
              const filler=document.createElement('section');
              filler.dataset.auditFiller='1';
              filler.style.cssText='height:1700px;pointer-events:none;';
              content.appendChild(filler);
              dialog.showModal();
            }""")
            rect=locator.bounding_box()
            content=locator.locator(":scope > form, :scope > .provision-pix-content")
            inner=content.bounding_box()
            state=locator.evaluate("""(dialog)=>{
              const form=dialog.querySelector(':scope > form, :scope > .provision-pix-content');
              return {
                dialogOverflow:getComputedStyle(dialog).overflowY,
                contentOverflow:getComputedStyle(form).overflowY,
                scrollHeight:form.scrollHeight,clientHeight:form.clientHeight,
                borderRadius:parseFloat(getComputedStyle(dialog).borderTopRightRadius),
                innerWidth:form.scrollWidth,clientWidth:form.clientWidth
              };
            }""")
            assert rect and inner,(id,width,"modal invisível")
            assert state["borderRadius"]>=17,(id,width,state)
            if width>850:
                assert state["dialogOverflow"]=="hidden",(id,width,state)
                assert state["contentOverflow"]=="auto",(id,width,state)
                assert state["scrollHeight"]>state["clientHeight"]+500,(id,width,state)
                assert inner["y"]-rect["y"]>=8,(id,width,"trilho toca topo",rect,inner)
                assert rect["y"]+rect["height"]-(inner["y"]+inner["height"])>=8,(
                    id,width,"trilho toca base",rect,inner)
                content.evaluate("(node)=>{node.scrollTop=240;}")
                assert content.evaluate("(node)=>node.scrollTop")>=200,(id,width)
            else:
                # O controlador iOS continua rolando o dialog, não o form.
                assert state["dialogOverflow"]=="auto",(id,width,state)
                assert rect["x"]>=0 and rect["x"]+rect["width"]<=width+1,(id,width,rect)
                assert rect["y"]>=0 and rect["y"]+rect["height"]<=height+1,(id,width,rect)
                locator.evaluate("(node)=>{node.scrollTop=240;}")
                assert locator.evaluate("(node)=>node.scrollTop")>=200,(id,width)
            locator.evaluate("""(dialog)=>{
              dialog.close();
              dialog.querySelector('[data-audit-filler]')?.remove();
            }""")
        print(f"AXORA: {len(ids)} modais auditados em viewport {width}x{height}")
        context.close()
    browser.close()
