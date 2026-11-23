"""Confere em Chromium o formulário familiar de provisão e entrada.

Não realiza login, não grava registros e não altera saldos.
"""
import os
import shutil
from playwright.sync_api import sync_playwright

URL = os.environ.get("AXORA_SMOKE_URL", "http://127.0.0.1:18081/")
CHROME = next((shutil.which(browser) for browser in
               ("google-chrome", "chromium", "chromium-browser")
               if shutil.which(browser)), None)
assert CHROME, "Chromium não encontrado"

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        executable_path=CHROME, headless=True, args=["--no-sandbox"])
    for width, height in [(390, 844), (1366, 900)]:
        context = browser.new_context(viewport={"width": width, "height": height})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_function("typeof window.AxoraFamily === 'object'")
        page.evaluate("""() => {
            document.querySelector('#login').classList.add('hidden');
            document.querySelector('#workspace').classList.remove('hidden');
            document.querySelector('#family-entry-dialog').showModal();
        }""")
        def change(kind, provision):
            page.evaluate("""({kind, provision}) => {
                const form=document.querySelector('#family-entry-form');
                form.dataset.occurrenceId=provision?'123':'';
                const choice=form.elements.classification;
                choice.disabled=false;
                choice.value=kind;
                choice.dispatchEvent(new Event('change',{bubbles:true}));
            }""", {"kind": kind, "provision": provision})

        change("SAÍDA", True)
        assert page.locator("#family-income-recipient-wrap").is_hidden(), (
            width, "Campo exclusivo de receita visível em pagamento")
        assert page.locator("#family-income-wallet-fieldset").is_hidden()
        assert page.locator("#family-cost-fieldset").is_visible()
        assert page.locator("#family-entry-form button[type='submit']").inner_text() == "Confirmar pagamento"
        assert page.locator("#family-entry-heading").inner_text() == "Pagar provisão com rateio"

        change("ENTRADA", False)
        assert page.locator("#family-income-recipient-wrap").is_visible(), (
            width, "Campo de recebedor ausente em entrada")
        assert page.locator("#family-cost-fieldset").is_hidden()
        assert page.locator("#family-entry-form button[type='submit']").inner_text() == "Salvar entrada"

        change("SAÍDA", True)
        assert page.locator("#family-income-recipient-wrap").is_hidden(), (
            width, "Campo reapareceu ao voltar para quitação")
        assert page.locator("#family-cost-fieldset").is_visible()
        assert page.locator("#family-entry-form button[type='submit']").inner_text() == "Confirmar pagamento"
        assert not errors, (width, errors)
        print(f"AXORA modal de quitação/entrada: {width}x{height} OK")
        context.close()
    browser.close()
