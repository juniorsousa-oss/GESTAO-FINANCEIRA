"""Regressão visual do QR Pix assíncrono e datas nativas nos cards iPhone.

Sem QR real, credenciais ou mutação financeira. QR de teste é SVG sintético,
apenas para medir expansão e rolagem do dialog após a carga.
"""
import os
import shutil
from playwright.sync_api import sync_playwright

URL=os.environ.get("AXORA_SMOKE_URL","http://127.0.0.1:18081/")
CHROME=next((shutil.which(s) for s in
             ("google-chrome","chromium","chromium-browser") if shutil.which(s)),None)
assert CHROME,"Chromium ausente"

with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=CHROME,headless=True,args=["--no-sandbox"])
    for width,height in [(320,640),(360,740),(390,844),(430,932),(820,780)]:
        context=browser.new_context(
            viewport={"width":width,"height":height},
            device_scale_factor=2,is_mobile=True,has_touch=True,locale="pt-BR")
        page=context.new_page()
        page.goto(URL,wait_until="domcontentloaded")
        page.wait_for_function("typeof window.AxoraActionMenus === 'object'")
        page.evaluate("""() => {
          document.querySelector('#login').classList.add('hidden');
          document.querySelector('#workspace').classList.remove('hidden');
          const dlg=document.querySelector('#provision-pix-dialog');
          document.querySelector('#provision-pix-description').textContent=
            'Pagamento de teste · vencimento 06/11/2026';
          document.querySelector('#provision-pix-result').hidden=true;
          document.querySelector('#provision-pix-loading').hidden=false;
          dlg.showModal();
        }""")
        page.wait_for_timeout(130)
        pix=page.locator("#provision-pix-dialog")
        initial=pix.bounding_box()
        assert initial and initial["x"]>=0 and initial["x"]+initial["width"]<=width+1
        assert not pix.evaluate("(d)=>Boolean(d.dataset.axoraFixedHeight)"),(
            width,"Pix foi congelado antes da API")
        page.evaluate("""() => {
          const pixels='<svg xmlns="http://www.w3.org/2000/svg" width="264" height="264" viewBox="0 0 264 264">'+
            '<rect width="264" height="264" fill="white"/>'+
            '<rect x="12" y="12" width="45" height="45" fill="black"/>'+
            '<rect x="207" y="12" width="45" height="45" fill="black"/>'+
            '<rect x="12" y="207" width="45" height="45" fill="black"/></svg>';
          document.querySelector('#provision-pix-image').src=
            'data:image/svg+xml;charset=utf-8,'+encodeURIComponent(pixels);
          document.querySelector('#provision-pix-copy-text').value=
            '000201'+('PIX-TESTE-NENHUM-VALOR-REAL'.repeat(15));
          document.querySelector('#provision-pix-loading').hidden=true;
          document.querySelector('#provision-pix-result').hidden=false;
          document.querySelector('#provision-pix-copy-button').disabled=false;
        }""")
        page.wait_for_timeout(100)
        final=pix.bounding_box()
        assert final and final["height"]>initial["height"]+160,(
            width,"Modal não aumentou quando QR chegou",initial,final)
        assert final["height"]<=height-15,(
            width,"Modal Pix maior que a tela",final)
        assert not pix.evaluate("(d)=>Boolean(d.dataset.axoraFixedHeight)")
        image=page.locator("#provision-pix-image")
        assert image.evaluate("(img)=>img.complete && img.naturalWidth>0")
        qr=image.bounding_box()
        assert qr and qr["width"]>=180 and qr["height"]>=180
        assert qr["x"]>=final["x"] and qr["x"]+qr["width"]<=final["x"]+final["width"]+1
        # QR deve ser acessível na rolagem do próprio modal, não na página.
        image.evaluate("(img)=>img.scrollIntoView({block:'nearest'})")
        page.wait_for_timeout(60)
        rect=image.bounding_box()
        modal=pix.bounding_box()
        assert rect["y"]>=modal["y"]-2 and rect["y"]+rect["height"]<=modal["y"]+modal["height"]+2,(
            width,"QR Pix cortado dentro do modal",rect,modal)
        pix.evaluate("(d)=>{d.scrollTop=d.scrollHeight;}")
        page.wait_for_timeout(60)
        copy=page.locator("#provision-pix-copy-button").bounding_box()
        modal=pix.bounding_box()
        assert copy and copy["y"]+copy["height"]<=modal["y"]+modal["height"]+2,(
            width,"Copiar Pix inacessível",copy,modal)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        pix.evaluate("(d)=>d.close()")
        # Campos date nativos em formulários variados (não só Provisões).
        for modal_id in ("provision-dialog","provision-edit-dialog",
                         "provision-payment-dialog","debt-agreement-dialog",
                         "bank-transaction-dialog","family-entry-dialog"):
            dialog=page.locator("#"+modal_id)
            dialog.evaluate("(d)=>d.showModal()")
            page.wait_for_timeout(60)
            outer=dialog.bounding_box()
            assert outer and outer["x"]>=0 and outer["x"]+outer["width"]<=width+1
            for date_field in dialog.locator('input[type="date"]').all():
                if not date_field.is_visible():continue
                date_field.evaluate("(el)=>el.value='2026-11-06'")
                bounds=date_field.bounding_box()
                assert bounds, (width,modal_id,"date field not laid out")
                assert bounds["x"]>=outer["x"]-1, (width,modal_id,bounds,outer)
                assert bounds["x"]+bounds["width"]<=outer["x"]+outer["width"]-6,(
                    width,modal_id,"Data excede card",bounds,outer)
                assert date_field.evaluate(
                    "(el)=>getComputedStyle(el).boxSizing")=="border-box"
                assert date_field.evaluate(
                    "(el)=>getComputedStyle(el).minWidth")=="0px"
            dialog.evaluate("(d)=>d.close()")
        print(f"AXORA iOS Pix e datas: {width}x{height} OK")
        context.close()
    browser.close()
