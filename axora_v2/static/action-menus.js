/* AXORA — Gerenciador único dos menus de ações dos cards.
 * Nunca altera as dimensões do card; apenas menus de ações, não acordeões.
 * Funciona com cards recriados por render(), mouse, toque e teclado.
 */
(()=>{
  "use strict";
  const selector="details.axora-action-menu";
  let active=null;
  function closeAll({restoreFocus=false}={}){
    const current=active;
    document.querySelectorAll(selector+"[open]").forEach(menu=>{
      menu.open=false;
      menu.removeAttribute("data-menu-positioned");
      menu.querySelector(":scope > summary")?.setAttribute("aria-expanded","false");
    });
    active=null;
    if(restoreFocus&&current?.isConnected)
      current.querySelector(":scope > summary")?.focus({preventScroll:true});
  }
  function position(menu){
    if(!menu?.open||!menu.isConnected)return;
    const trigger=menu.querySelector(":scope > summary");
    const panel=menu.querySelector(":scope > .axora-action-menu-panel");
    if(!trigger||!panel)return;
    const viewport=window.visualViewport;
    const width=viewport?.width||document.documentElement.clientWidth||window.innerWidth;
    const height=viewport?.height||document.documentElement.clientHeight||window.innerHeight;
    const ox=viewport?.offsetLeft||0;
    const oy=viewport?.offsetTop||0;
    const t=trigger.getBoundingClientRect();
    // O painel está fora do fluxo; medir antes de mostrar evita piscadas.
    menu.removeAttribute("data-menu-positioned");
    const w=panel.offsetWidth,h=panel.offsetHeight,gap=7,pad=12;
    const left=Math.max(ox+pad,Math.min(t.right-w,ox+width-w-pad));
    const below=oy+height-t.bottom-gap,above=t.top-oy-gap;
    const top=(h>below&&above>below)
      ?Math.max(oy+pad,t.top-gap-h)
      :Math.min(t.bottom+gap,oy+height-pad-h);
    panel.style.left=Math.round(left)+"px";
    panel.style.top=Math.round(Math.max(oy+pad,top))+"px";
    menu.setAttribute("data-menu-positioned","true");
  }
  function open(menu){
    if(!menu||!menu.isConnected)return;
    const wasOpen=menu.open;
    closeAll();
    if(wasOpen)return;
    menu.open=true;
    active=menu;
    menu.querySelector(":scope > summary")?.setAttribute("aria-expanded","true");
    position(menu);
  }
  document.addEventListener("click",e=>{
    const target=e.target;
    if(!(target instanceof Element))return;
    const summary=target.closest(selector+" > summary");
    if(summary){
      // A alternância nativa do details não pode reabrir um menu fechado.
      e.preventDefault();
      open(summary.parentElement);
      return;
    }
    const menu=target.closest(selector);
    if(menu){
      // Controles de formulário (select/inputs) permanecem abertos.
      if(target.closest("button,[data-action],[data-family-action],a[href]"))
        queueMicrotask(closeAll);
      return;
    }
    closeAll();
  },true);
  document.addEventListener("keydown",e=>{
    if(e.key==="Escape"&&document.querySelector(selector+"[open]")){
      e.preventDefault();
      e.stopPropagation();
      closeAll({restoreFocus:true});
    }
  },true);
  // Abrir programaticamente ou pelo teclado também respeita exclusividade.
  document.addEventListener("toggle",e=>{
    const menu=e.target;
    if(!(menu instanceof HTMLDetailsElement)||!menu.matches(selector))return;
    if(menu.open){
      document.querySelectorAll(selector+"[open]").forEach(other=>{
        if(other!==menu){
          other.open=false;
          other.removeAttribute("data-menu-positioned");
          other.querySelector(":scope > summary")?.setAttribute("aria-expanded","false");
        }
      });
      active=menu;
      menu.querySelector(":scope > summary")?.setAttribute("aria-expanded","true");
      position(menu);
    }else{
      menu.removeAttribute("data-menu-positioned");
      menu.querySelector(":scope > summary")?.setAttribute("aria-expanded","false");
      if(active===menu)active=null;
    }
  },true);
  // Um menu antigo não deve ficar deslocado ao rolar/navegar.
  window.addEventListener("scroll",()=>{if(active)closeAll()},true);
  window.addEventListener("resize",()=>{if(active)position(active)});
  if(window.visualViewport)
    window.visualViewport.addEventListener("resize",()=>{if(active)position(active)});
  window.AxoraActionMenus={close:closeAll,position};
})();
