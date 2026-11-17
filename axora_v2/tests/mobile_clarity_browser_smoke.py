"""Auditoria de leitura mobile AXORA sem credenciais ou lançamentos reais.
Confere cartões, filtros recolhíveis, menu contextual e desktop preservado.
"""
import os
import shutil
from playwright.sync_api import sync_playwright

URL=os.environ.get("AXORA_SMOKE_URL","http://127.0.0.1:18081/")
CHROME=next((shutil.which(s) for s in
             ("google-chrome","chromium","chromium-browser") if shutil.which(s)),None)
assert CHROME,"Chromium não instalado"

INIT="""() => {
  document.querySelector('#login').classList.add('hidden');
  document.querySelector('#workspace').classList.remove('hidden');
  me={id:1,display_name:'Principal fictício',family_enabled:true,family_role:'principal'};
  bankingData={mode:'manual',accounts:[],holders:[],balances:null};
  provisionItems=[
    {id:101,rule_id:9,due_date:'2026-10-20',planned_value:87.60,
      visibility_label:'casal',
      rule:{description:'Internet AP',category:'Moradia',responsible:'Principal fictício',
        payment_method:'link',payment_url:'https://example.org/consulta',
        recurrence:'unlimited',frequency:'monthly',value_mode:'variable'}},
    {id:102,rule_id:10,due_date:'2026-10-22',planned_value:99.07,
      visibility_label:'privado',
      rule:{description:'Cemig',category:'Moradia',responsible:'Familiar fictício',
        payment_method:'link',payment_url:'https://example.org/consulta',
        recurrence:'unlimited',frequency:'monthly',value_mode:'variable'}},
    {id:103,rule_id:11,due_date:'2026-11-22',planned_value:29.90,
      visibility_label:'privado',
      rule:{description:'Telefonia',category:'Comunicação',responsible:'Principal fictício',
        payment_method:'none',recurrence:'unlimited',frequency:'monthly',
        value_mode:'fixed'}},
  ];
  provisionView='all';
  provisionFiltersExpanded=false;
  Object.keys(provisionFilters).forEach(k=>provisionFilters[k]='');
  document.querySelector('#page-content').innerHTML=provisionsPage();
}"""
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=CHROME,headless=True,args=["--no-sandbox"])
    for width,height in [(360,780),(390,844),(430,932),(820,780),(1366,900)]:
        mobile=width<=850
        context=browser.new_context(
            viewport={"width":width,"height":height},
            is_mobile=mobile,has_touch=mobile,device_scale_factor=1)
        page=context.new_page()
        page.goto(URL,wait_until="domcontentloaded")
        page.wait_for_function("typeof provisionsPage==='function' && typeof bankInfoBanner==='function'")
        page.evaluate(INIT)
        rows=page.locator(".provision-table tbody tr")
        assert rows.count()==3,(width,"vencimentos não exibidos")
        first=rows.nth(0)
        second=rows.nth(1)
        details=page.locator(".provision-filter-disclosure")
        info=page.locator(".provision-info-disclosure")
        if mobile:
            assert not details.evaluate("(e)=>e.open"),"Filtros devem iniciar recolhidos"
            assert info.count()==1 and not info.evaluate("(e)=>e.open"),"Aviso extenso aberto no mobile"
            assert page.locator(".provision-info-copy").is_hidden()
            assert page.locator(".provision-secondary-desktop").first.is_hidden()
            assert page.locator(".provision-row-actions .provision-site-link").first.is_visible()
            assert page.locator(".provision-row-actions > .btn.primary").first.is_visible()
            first_rect=first.bounding_box()
            second_rect=second.bounding_box()
            assert first_rect and second_rect
            assert second_rect["y"]>=first_rect["y"]+first_rect["height"]+9,(
                width,"cards de provisões encavalados",first_rect,second_rect)
            assert first_rect["x"]>=0 and first_rect["x"]+first_rect["width"]<=width+1
            details.locator(":scope > summary").click()
            assert details.evaluate("(el)=>el.open")
            for field in ("#provision-from-filter","#provision-to-filter",
                          "#provision-filter","#provision-category-filter"):
                rect=page.locator(field).bounding_box()
                assert rect and rect["width"]>100,(width,field,rect)
                assert rect["x"]>=0 and rect["x"]+rect["width"]<=width+1,(
                    width,"campo excedeu a largura da tela",field,rect)
            # Filtro pode ser fechado sem apagar os valores informados.
            page.locator("#provision-category-filter").select_option("Moradia")
            # Atualizar repinta o módulo; expansão permanece após a mudança.
            assert page.locator(".provision-filter-disclosure").evaluate("(el)=>el.open")
            page.locator(".provision-filter-disclosure > summary").click()
            assert not page.locator(".provision-filter-disclosure").evaluate("(el)=>el.open")
            page.evaluate("document.querySelector('#page-content').innerHTML=provisionsPage()")
            assert not page.locator(".provision-filter-disclosure").evaluate("(el)=>el.open")
            assert page.locator("#provision-category-filter").input_value()=="Moradia"
            # Ações secundárias não aumentam card nem alteram o layout de lista.
            page.locator(".provision-mobile-actions > summary").first.click()
            menu=page.locator(".provision-mobile-actions").first
            page.wait_for_function("document.querySelector('.provision-mobile-actions').open")
            panel=page.locator(".provision-mobile-actions-panel").first
            popup=panel.bounding_box()
            assert popup and popup["x"]>=0 and popup["x"]+popup["width"]<=width+1
            assert popup["y"]>=0 and popup["y"]+popup["height"]<=height+1
            assert "Editar" in panel.inner_text() and "Excluir" in panel.inner_text()
            assert abs(first.bounding_box()["height"]-first_rect["height"])<2,(
                width,"abrir menu altera altura do card")
            page.mouse.click(5,5)
            assert not menu.evaluate("(el)=>el.open"),"Menu não fechou ao clicar fora"
            bank=page.evaluate("bankInfoBanner()")
            assert '<details' in bank and 'bank-info-disclosure' in bank
        else:
            assert page.locator(".provision-info-disclosure").count()==0
            assert page.locator(".provision-module > .notice").is_visible()
            assert details.evaluate("(e)=>e.open")
            assert details.locator(":scope > summary").is_hidden()
            assert page.locator(".provision-row-actions [data-action='edit-provision']").first.is_visible()
            assert page.locator(".provision-mobile-actions").first.is_hidden()
            assert '<details' not in page.evaluate("bankInfoBanner()")
        # Dashboard mantém ações gerais, nunca inclui o atalho de rateio.
        dashboard_actions=page.evaluate("() => { page='dashboard'; return actionButtons(); }")
        assert 'data-family-action="new-expense"' not in dashboard_actions
        assert "Exportar Excel" in dashboard_actions
        context.close()
        print(f"AXORA mobile audit: {width}x{height} validado")
    browser.close()
