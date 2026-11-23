"""Teste Chromium do modal de reversão AXORA — sem credenciais ou mutações financeiras."""
import os
import shutil
from playwright.sync_api import sync_playwright

URL = os.environ.get("AXORA_SMOKE_URL", "http://127.0.0.1:18081/")
CHROME = next((shutil.which(x) for x in
    ("google-chrome", "chromium", "chromium-browser") if shutil.which(x)), None)
assert CHROME, "Chromium indisponível"

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        executable_path=CHROME, headless=True, args=["--no-sandbox"])
    for width, height in ((320, 700), (390, 844), (1366, 900)):
        context = browser.new_context(viewport={"width": width, "height": height})
        tab = context.new_page()
        errors = []
        tab.on("pageerror", lambda error: errors.append(str(error)))
        tab.goto(URL, wait_until="domcontentloaded")
        tab.wait_for_function(
            "typeof moduleTable==='function' && typeof window.AxoraFamily==='object'")
        tab.evaluate("""() => {
            document.querySelector('#login').classList.add('hidden');
            document.querySelector('#workspace').classList.remove('hidden');
            me={id:12,display_name:'Principal teste',family_enabled:true,
                family_role:'principal',csrf:'test-only'};
            page='movements';
            const record={
                id:901,provision_occurrence_id:409,movement_date:'2026-11-20',
                description:'Fotos Formatura',value:91.05,
                classification:'SAÍDA',category:'Educação',competence:'11/2026',
                fixed_variable:'VARIÁVEL',allocation_value:0
            };
            document.querySelector('#page-content').innerHTML=
                moduleTable('movements',[record]);
            window.__undoCalls=[];
            window.__toast='';
            window.__preview={
                occurrence_id:409,paid_amount:91.05,restored_wallet_amount:91.05,
                linked_existing_record:false,needs_reference:true,bank_linked:false
            };
            api=async (path,opts={})=>{
                window.__undoCalls.push({path,opts});
                if(path.endsWith('/reversal-preview')) return window.__preview;
                if(path.endsWith('/undo')) return {ok:true,status:'open',
                    occurrence_id:409,restored_wallet_amount:window.__preview.restored_wallet_amount};
                if(path==='/api/family')return {
                    profiles:[{id:1,display_name:'Principal teste',active:true,
                        relationship:'principal'}],my_profile_id:1
                };
                if(path==='/api/family/summary')return {};
                throw Error('Unexpected endpoint '+path);
            };
            window.confirm=()=>{throw Error('native confirm must not be called')};
            window.prompt=()=>{throw Error('native prompt must not be called')};
            refresh=async()=>{};
            loadBanking=async()=>{};
            showToast=value=>{window.__toast=value};
        }""")
        button = tab.locator('[data-family-action="undo-provision-payment"]')
        assert button.count() == 1 and button.is_visible()
        modal = tab.locator("#family-reversal-dialog")
        button.click()
        modal.wait_for(state="visible")
        assert tab.locator("#family-reversal-description").inner_text() == "Fotos Formatura"
        assert tab.locator("#family-reversal-amount").inner_text() == "R$ 91,05"
        assert "R$ 91,05" in tab.locator("#family-reversal-wallet").inner_text()
        assert "retirado" in tab.locator("#family-reversal-record-note").inner_text()
        assert tab.locator("#family-reversal-reference-row").is_visible()
        assert tab.locator("#family-reversal-intro").is_visible()
        rect = modal.bounding_box()
        assert rect and rect["x"] >= 0 and rect["x"] + rect["width"] <= width+1
        assert rect["y"] >= 0 and rect["y"] + rect["height"] <= height+1
        # Cancelar não deve executar POST; o estado do modal deve limpar.
        modal.locator('[data-family-reversal-close]').last.click()
        assert not modal.is_visible()
        assert not any(c["path"].endswith("/undo")
                       for c in tab.evaluate("window.__undoCalls"))
        button.click()
        modal.wait_for(state="visible")
        tab.locator("#family-reversal-reference").fill("abc")
        modal.locator('button[type="submit"]').click()
        assert tab.locator("#family-reversal-error").is_visible()
        assert not any(c["path"].endswith("/undo")
                       for c in tab.evaluate("window.__undoCalls"))
        tab.locator("#family-reversal-reference").fill("74,50")
        modal.locator('button[type="submit"]').click()
        tab.wait_for_function(
            "() => window.__undoCalls.some(c=>c.path.endsWith('/undo'))")
        payload = tab.evaluate("""() => JSON.parse(
            window.__undoCalls.find(c=>c.path.endsWith('/undo')).opts.body)""")
        assert payload == {"confirm": True, "reference_value": 74.50}, payload
        modal.wait_for(state="hidden")
        assert "Provisão reaberta" in tab.evaluate("window.__toast")

        # Registro preexistente e sem débito: nenhum campo extra, nenhum estorno fictício.
        tab.evaluate("""() => {
          window.__preview={occurrence_id:409,paid_amount:91.05,
            restored_wallet_amount:0,linked_existing_record:true,
            needs_reference:false,bank_linked:false};
          window.__undoCalls=[];
        }""")
        button.click()
        modal.wait_for(state="visible")
        assert tab.locator("#family-reversal-reference-row").is_hidden()
        assert "Nenhum saldo" in tab.locator("#family-reversal-wallet").inner_text()
        assert "preservado" in tab.locator("#family-reversal-record-note").inner_text()
        modal.locator('button[type="submit"]').click()
        tab.wait_for_function(
            "() => window.__undoCalls.some(c=>c.path.endsWith('/undo'))")
        payload = tab.evaluate("""() => JSON.parse(
            window.__undoCalls.find(c=>c.path.endsWith('/undo')).opts.body)""")
        assert payload == {"confirm": True}, payload
        modal.wait_for(state="hidden")
        assert not errors, (width, errors)
        print(f"AXORA modal de reversão {width}x{height}: OK")
        context.close()
    browser.close()
