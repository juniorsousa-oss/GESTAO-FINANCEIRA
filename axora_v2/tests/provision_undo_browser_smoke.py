"""Teste Chromium do botao de reversao sem credenciais nem dados reais."""
import os
import shutil
from playwright.sync_api import sync_playwright

URL = os.environ.get("AXORA_SMOKE_URL", "http://127.0.0.1:18081/")
CHROME = next((shutil.which(x) for x in
    ("google-chrome", "chromium", "chromium-browser") if shutil.which(x)), None)
assert CHROME, "Chromium indisponivel"

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        executable_path=CHROME, headless=True, args=["--no-sandbox"])
    for width, height in ((390, 844), (1366, 900)):
        context = browser.new_context(viewport={"width": width, "height": height})
        tab = context.new_page()
        errors = []
        tab.on("pageerror", lambda error: errors.append(str(error)))
        tab.goto(URL, wait_until="domcontentloaded")
        tab.wait_for_function("typeof moduleTable==='function' && typeof window.AxoraFamily==='object'")
        tab.evaluate("""() => {
            document.querySelector('#login').classList.add('hidden');
            document.querySelector('#workspace').classList.remove('hidden');
            me={id:12,display_name:'Principal teste',family_enabled:true,
                family_role:'principal',csrf:'test-only'};
            page='movements';
            const record={
                id:901,provision_occurrence_id:409,movement_date:'2026-11-20',
                description:'Despesa hipotetica',value:91.05,
                classification:'SAÍDA',category:'Teste',competence:'11/2026',
                fixed_variable:'VARIÁVEL',allocation_value:0
            };
            document.querySelector('#page-content').innerHTML=
                moduleTable('movements',[record]);
            window.__undoCalls=[];
            window.__toast='';
            api=async (path,opts={})=>{
                window.__undoCalls.push({path,opts});
                if(path.endsWith('/reversal-preview')) return {
                    occurrence_id:409,paid_amount:91.05,restored_wallet_amount:91.05,
                    linked_existing_record:false,needs_reference:true,bank_linked:false
                };
                if(path.endsWith('/undo'))return {ok:true,status:'open',
                    occurrence_id:409,restored_wallet_amount:91.05};
                if(path==='/api/family')return {
                    profiles:[{id:1,display_name:'Principal teste',active:true,
                      relationship:'principal'}],my_profile_id:1
                };
                if(path==='/api/family/summary')return {};
                throw Error('Unexpected endpoint '+path);
            };
            confirm=()=>true;
            prompt=()=> '74,50';
            refresh=async()=>{};
            loadBanking=async()=>{};
            showToast=(value)=>{window.__toast=value;};
        }""")
        button = tab.locator('[data-family-action="undo-provision-payment"]')
        assert button.count() == 1 and button.is_visible(), (
            width, "Estorno nao apareceu para principal")
        button.click()
        tab.wait_for_function("""() => window.__undoCalls.some(x=>x.path.endsWith('/undo'))""")
        body=tab.evaluate("""() => JSON.parse(window.__undoCalls.find(x=>x.path.endsWith('/undo')).opts.body)""")
        assert body == {"confirm": True, "reference_value": 74.50}, (width,body)
        assert not errors, (width,errors)
        print(f"AXORA estorno principal Chromium {width}x{height}: OK")
        context.close()
    browser.close()
