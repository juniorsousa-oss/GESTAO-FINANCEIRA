"""Chromium: exclusão manual no AXORA sem alterar dados ou saldos reais."""
import os
import shutil
from playwright.sync_api import sync_playwright

URL = os.environ.get("AXORA_SMOKE_URL", "http://127.0.0.1:18081/")
CHROME = next((shutil.which(x) for x in
    ("google-chrome","chromium","chromium-browser") if shutil.which(x)),None)
assert CHROME

with sync_playwright() as playwright:
    browser=playwright.chromium.launch(
        executable_path=CHROME,headless=True,args=["--no-sandbox"])
    for width,height in ((320,700),(390,844),(1366,900)):
        context=browser.new_context(viewport={"width":width,"height":height})
        page=context.new_page()
        errors=[]
        page.on("pageerror",lambda error:errors.append(str(error)))
        page.goto(URL,wait_until="domcontentloaded")
        page.wait_for_function("typeof moduleTable==='function' && typeof window.AxoraFamily==='object'")
        page.evaluate("""() => {
          document.querySelector('#login').classList.add('hidden');
          document.querySelector('#workspace').classList.remove('hidden');
          me={id:12,display_name:'Principal teste',family_enabled:true,
             family_role:'principal',csrf:'test-only'};
          page='movements';
          const row={
            id:901,provision_occurrence_id:null,movement_date:'2026-11-18',
            description:'Bolsa Família',value:864,
            classification:'ENTRADA',category:'Fonte de Renda',
            competence:'11/2026',fixed_variable:'VARIÁVEL',allocation_value:0
          };
          document.querySelector('#page-content').innerHTML=moduleTable('movements',[row]);
          window.__calls=[];
          window.__toast='';
          window.__preview={
            id:901,description:'Bolsa Família',classification:'ENTRADA',
            amount:864,wallet_delta:-750,
            credited_reversed:750,debited_restored:0,has_wallet_effect:true
          };
          api=async (path,opts={})=>{
            window.__calls.push({path,opts});
            if(path.endsWith('/delete-preview'))return window.__preview;
            if(opts.method==='DELETE')return {
              ok:true,deleted_id:901,wallet_delta:window.__preview.wallet_delta
            };
            if(path==='/api/family')return {
              profiles:[{id:1,display_name:'Principal teste',
                active:true,relationship:'principal'}],my_profile_id:1
            };
            if(path==='/api/family/summary')return {};
            throw Error('Unexpected endpoint: '+path);
          };
          window.confirm=()=>{throw Error('Exclusão não deve usar confirm nativo')};
          refresh=async()=>{};
          loadBanking=async()=>{};
          showToast=text=>{window.__toast=text};
        }""")
        delete_button=page.locator('[data-action="delete"][data-kind="movements"]')
        assert delete_button.count()==1 and delete_button.is_visible()
        modal=page.locator("#family-manual-delete-dialog")
        delete_button.click()
        modal.wait_for(state="visible")
        assert page.locator("#family-manual-delete-description").inner_text()=="Bolsa Família"
        assert "R$ 864,00" in " ".join(
            page.locator("#family-manual-delete-amount").inner_text().split())
        assert "R$ 750,00" in " ".join(
            page.locator("#family-manual-delete-wallet").inner_text().split())
        assert "R$ 750,00" in " ".join(
            page.locator("#family-manual-delete-explanation").inner_text().split())
        rect=modal.bounding_box()
        assert rect and rect["x"]>=0 and rect["x"]+rect["width"]<=width+1
        assert rect["y"]>=0 and rect["y"]+rect["height"]<=height+1
        # Cancelar/fechar nunca deve enviar DELETE.
        modal.locator("[data-manual-delete-close]").last.click()
        modal.wait_for(state="hidden")
        assert not any(c["opts"].get("method")=="DELETE"
                for c in page.evaluate("window.__calls"))
        delete_button.click()
        modal.wait_for(state="visible")
        modal.locator('button[type="submit"]').click()
        page.wait_for_function(
          "() => window.__calls.some(c=>c.opts.method==='DELETE')")
        calls=page.evaluate("window.__calls")
        assert len([c for c in calls if c["opts"].get("method")=="DELETE"])==1
        modal.wait_for(state="hidden")
        assert "Saldo" in page.evaluate("window.__toast")

        # Histórico manual sem efeito na carteira: zero ajuste.
        page.evaluate("""() => {
          window.__calls=[];
          window.__preview={id:901,description:'Histórico',
            classification:'ENTRADA',amount:100,wallet_delta:0,
            credited_reversed:0,debited_restored:0,
            has_wallet_effect:false};
        }""")
        delete_button.click()
        modal.wait_for(state="visible")
        assert "Nenhum saldo" in page.locator("#family-manual-delete-wallet").inner_text()
        modal.locator('button[type="submit"]').click()
        page.wait_for_function(
          "() => window.__calls.some(c=>c.opts.method==='DELETE')")
        modal.wait_for(state="hidden")
        assert not errors,(width,errors)
        print(f"AXORA exclusão manual {width}x{height} OK")
        context.close()
    browser.close()
