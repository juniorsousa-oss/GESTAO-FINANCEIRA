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
    # Titulares vêm de um único endpoint e agora vivem nas Configurações.
    page.evaluate("""() => {
      me={id:1,display_name:"Principal fictício",family_enabled:true,family_role:"principal"};
      bankingData={
        mode:"manual",holders:[
          {id:1,name:"Titular A",relationship:"proprio"},
          {id:2,name:"Parente B",relationship:"conjuge"},
          {id:3,name:"Pessoa com nome composto extenso",relationship:"mae"},
          {id:4,name:"Familiar C",relationship:"pai"}
        ],
        accounts:Array.from({length:7},(_,i)=>({
          id:i+10,holder_id:i<4?1:i===4?2:i===5?3:4,
          bank_name:"Banco fictício",nickname:"Carteira de teste "+i,
          account_type:"corrente",manual_balance:100+i,
          visibility_label:"privado"
        })),
        balances:{
          holders:[{holder_id:1,known:4,missing:0,total:406},
                   {holder_id:2,known:1,missing:0,total:104},
                   {holder_id:3,known:1,missing:0,total:105},
                   {holder_id:4,known:1,missing:0,total:106}],
          known_accounts:7,missing_accounts:0,
          personal:406,family:315,combined:721,personal_missing:0,family_missing:0
        }
      };
      bankingError=null;
      document.querySelector("#page-content").innerHTML=bankingHolderCatalogPanel();
    }""")
    cards=page.locator("#page-content .bank-entity")
    assert cards.count()==4
    assert page.locator("#bank-holder-settings").is_visible()
    assert page.locator("#bank-holder-settings .panel-heading h2").inner_text()=="Membros cadastrados"
    for i in range(cards.count()):
        card=cards.nth(i)
        bounds=card.bounding_box()
        buttons=card.locator(".bank-entity-actions .btn")
        assert bounds and bounds["height"]<155, ("holder card too tall",i,bounds)
        assert buttons.count()==2
        first,second=buttons.nth(0).bounding_box(),buttons.nth(1).bounding_box()
        assert first and second
        assert abs(first["y"]-second["y"])<=2, ("buttons stacked",i,first,second)
        assert first["x"]+first["width"]<second["x"]+1, ("buttons overlapped",i)
        assert second["x"]+second["width"]<=bounds["x"]+bounds["width"]+1
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")

    # Contas: abertura de uma pessoa NÃO altera a altura de nenhuma outra.
    page.set_viewport_size({"width":1366,"height":900})
    page.evaluate("""() => {
      snapshot={settings:{},summary:{}};
      page="bank-accounts";
      render();
    }""")
    assert page.locator("#page-content .bank-entity").count()==0
    person_cards=page.locator("#page-content .bank-person-card")
    assert person_cards.count()==4
    assert person_cards.first.locator(".bank-person-account").count()==4
    small_before=person_cards.nth(1).bounding_box()
    last_before=person_cards.nth(3).bounding_box()
    first_before=person_cards.first.bounding_box()
    person_cards.first.locator("summary.bank-person-summary").click()
    page.wait_for_timeout(140)
    first_after=person_cards.first.bounding_box()
    small_after=person_cards.nth(1).bounding_box()
    last_after=person_cards.nth(3).bounding_box()
    assert first_after["height"]>first_before["height"]+150
    assert abs(small_after["height"]-small_before["height"])<=2, (small_before,small_after)
    assert abs(last_after["height"]-last_before["height"])<=2, (last_before,last_after)
    assert small_after["y"]>=first_after["y"]+first_after["height"]+4, (small_after,first_after)
    assert page.locator("#page-content .bank-person-account").count()==7
    # Menu recolhido por padrão; opções visíveis só após os três pontos.
    card=page.locator(".bank-person-account").first
    menu=card.locator(".bank-account-menu")
    assert menu.count()==1
    assert not menu.get_attribute("open")
    assert not card.locator("[data-action='bank-open-investments']").is_visible()
    # O ícone deve pertencer ao cartão, sem ficar solto entre linhas.
    def assert_menu_inside_card(card):
        bounds=card.bounding_box()
        button=card.locator(".bank-account-menu > summary").bounding_box()
        assert bounds and button, ("missing account action",bounds,button)
        assert bounds["x"]+bounds["width"]-button["x"]-button["width"]>=6, (
            "action protrudes from card right edge",bounds,button)
        assert 5<=button["x"]-bounds["x"]<=bounds["width"]-button["width"]-5
        assert 6<=button["y"]-bounds["y"]<=45, (
            "action detached from card top (regression)",bounds,button)
        assert button["y"]+button["height"]<=bounds["y"]+bounds["height"]-8, (
            "action below card",bounds,button)

    for account in page.locator(".bank-person-card[open] .bank-person-account").all():
        assert_menu_inside_card(account)
    # Nenhum botão da carteira recolhida pode permanecer visível.
    for item in page.locator(".bank-person-card:not([open]) .bank-account-menu > summary").all():
        assert not item.is_visible(), "menu leaked from closed holder"
    menu.locator("summary").click()
    assert card.locator("[data-action='bank-open-investments']").is_visible()
    assert card.locator("[data-action='bank-transfer-open']").is_visible()
    assert_menu_inside_card(card)
    assert card.locator(".bank-account-menu-panel").bounding_box()["y"] < (
        card.bounding_box()["y"]+card.bounding_box()["height"])
    assert page.locator("#page-content .bank-entity").count()==0
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")

    # Preserva o acordeão da pessoa e o scroll. Menus contextuais são
    # recolhidos ao rolar ou atualizar conteúdo, nunca restaurados à força.
    page.evaluate("""() => {
      window.__accountTestNode=document.querySelector(".bank-person-card");
    }""")
    assert page.evaluate(
        "document.querySelector('.bank-person-card')===window.__accountTestNode")
    page.evaluate("render()")
    assert page.evaluate(
        "document.querySelector('.bank-person-card')===window.__accountTestNode"), (
        "unchanged data rebuilt the banking page")
    assert page.locator("details.bank-person-card").first.get_attribute("open") is not None
    assert page.locator("details.bank-account-menu").first.get_attribute("open") is not None
    page.evaluate("""() => {
      document.querySelector("#workspace .main-area").scrollTop=410;
      bankingData.accounts[0].manual_balance=999.12;
      render();
    }""")
    assert page.locator("details.bank-person-card").first.get_attribute("open") is not None
    assert page.locator("details.bank-account-menu").first.get_attribute("open") is None, (
        "menu de ações reaberto após atualização da página")
    assert "999,12" in page.locator(".bank-person-account").first.inner_text()
    assert page.locator("#workspace .main-area").evaluate("(el)=>el.scrollTop")>=400, (
        "scroll reset after balance update")
    assert_menu_inside_card(page.locator(".bank-person-account").first)

    # Formulários avançados, sem API real e sem modificar saldos.
    assert page.evaluate("Boolean(window.AxoraBankAdvanced)")
    page.evaluate("AxoraBankAdvanced.openTransfer(10)")
    transfer_form=page.locator("#bank-transfer-form")
    assert page.locator("#bank-transfer-dialog").is_visible()
    origin=transfer_form.locator('[name="from_account_id"]').input_value()
    destination=transfer_form.locator('[name="to_account_id"]').input_value()
    assert origin=="10" and destination!="10"
    page.locator("#bank-transfer-dialog").evaluate("(el)=>el.close()")
    page.evaluate("AxoraBankAdvanced.openInvestment(10)")
    assert page.locator("#bank-investment-dialog").is_visible()
    assert page.locator("#bank-investment-form [name='account_id']").input_value()=="10"
    page.locator("#bank-investment-dialog").evaluate("(el)=>el.close()")
    # Menus e modais fechados não devem causar rolagem horizontal indevida.
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")

    # Repetição em largura de iPhone com vários cartões internos.
    page.set_viewport_size({"width":390,"height":844})
    page.wait_for_timeout(90)
    assert page.locator("#page-content .bank-person-card").count()==4
    assert_menu_inside_card(page.locator(".bank-person-account").first)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")

    # O cadastro de titulares e outros formulários não dão zoom automático
    # (fonte de 16px) nem mudam suas dimensões ao abrir o teclado.
    page.evaluate("bankOpenHolder(1)")
    holder_dialog=page.locator("#bank-holder-dialog")
    assert holder_dialog.is_visible()
    page.wait_for_timeout(160)
    initial=holder_dialog.bounding_box()
    assert initial and initial["x"]>=0 and initial["x"]+initial["width"]<=391
    input_font=page.locator("#bh-name").evaluate(
        "(el)=>parseFloat(getComputedStyle(el).fontSize)")
    assert input_font>=16, ("iOS focus zoom risk",input_font)
    page.locator("#bh-name").focus()
    page.set_viewport_size({"width":390,"height":495})
    page.wait_for_timeout(200)
    focused=holder_dialog.bounding_box()
    assert focused
    for dimension in ("x","y","width","height"):
        assert abs(initial[dimension]-focused[dimension])<=2, (
            "dialog jumped with keyboard",dimension,initial,focused)
    assert focused["x"]>=0 and focused["x"]+focused["width"]<=391
    page.set_viewport_size({"width":390,"height":844})
    holder_dialog.evaluate("(el)=>el.close()")
    page.wait_for_timeout(70)

    # Cobrir os demais diálogos do aplicativo (registros, provisões, família)
    # sem navegar ou usar a base financeira real.
    for dialog_id in ("bank-account-dialog","bank-balance-dialog",
                      "bank-transaction-dialog","editor-dialog",
                      "provision-dialog","family-entry-dialog",
                      "family-access-dialog"):
        dlg=page.locator("#"+dialog_id)
        dlg.evaluate("(el)=>el.showModal()")
        page.wait_for_timeout(80)
        rect=dlg.bounding_box()
        assert rect and rect["x"]>=0 and rect["x"]+rect["width"]<=391, (
            dialog_id,rect)
        inputs=dlg.locator("input:not([type=hidden]):not([type=checkbox]):not([type=radio])")
        if inputs.count():
            font=inputs.first.evaluate("(el)=>parseFloat(getComputedStyle(el).fontSize)")
            assert font>=16, (dialog_id,font)
        dlg.evaluate("(el)=>el.close()")

    print("AXORA iPhone: teclado, diálogos estáveis e titulares compactos OK")
    browser.close()
