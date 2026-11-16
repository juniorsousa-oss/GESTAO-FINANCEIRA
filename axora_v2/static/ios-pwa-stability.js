/* AXORA iOS PWA: altura do login estável durante a abertura do teclado.
   Não usa foco forçado, zoom artificial, bloqueio de scroll nem guarda dados. */
(() => {
  const root=document.documentElement;
  const mobile=()=>window.matchMedia("(max-width: 900px)").matches;
  let lastWidth=window.innerWidth;

  function lockLoginStage(){
    if(!mobile()){
      root.style.removeProperty("--axora-login-stage-height");
      return;
    }
    const stage=Math.max(window.innerHeight,root.clientHeight);
    if(Number.isFinite(stage)&&stage>0){
      root.style.setProperty("--axora-login-stage-height",Math.round(stage)+"px");
    }
  }
  // No PWA o iOS não tem barra de navegador: esta altura cobre a tela,
  // inclusive por trás da status bar transparente.
  lockLoginStage();

  window.addEventListener("resize",()=>{
    const width=window.innerWidth;
    if(Math.abs(width-lastWidth)>2){
      lastWidth=width;
      // Mudança real de largura/orientação. A variação só de altura, típica
      // do teclado, NÃO altera a posição e dimensão da tela de login.
      if(document.activeElement?.id!=="login-password")lockLoginStage();
    }
  },{passive:true});

  window.addEventListener("orientationchange",()=>{
    window.setTimeout(()=>{
      lastWidth=window.innerWidth;
      if(document.activeElement?.id!=="login-password")lockLoginStage();
    },300);
  },{passive:true});

  // Diálogos internos: travar a geometria depois de showModal(), sem
  // recalcular a caixa durante o resize do teclado do Safari instalado.
  if(typeof document.querySelectorAll==="function" && typeof MutationObserver==="function"){
    const selector="dialog.editor-dialog,dialog.provision-dialog,dialog.bank-dialog,dialog.family-dialog";
    const modals=[...document.querySelectorAll(selector)];
    let viewportWidth=window.innerWidth;

    function openModal(){
      return modals.find(dialog=>dialog.open)||null;
    }
    function lockDialog(dialog){
      if(!dialog?.open || !mobile() || dialog.dataset.axoraFixedHeight)return;
      window.requestAnimationFrame(()=>{
        if(!dialog.open || !mobile() || dialog.dataset.axoraFixedHeight)return;
        const height=Math.ceil(dialog.getBoundingClientRect().height);
        if(height<80)return;
        dialog.style.setProperty("--axora-dialog-locked-height",height+"px");
        dialog.dataset.axoraFixedHeight="1";
      });
    }
    function clearDialog(dialog){
      dialog.style.removeProperty("--axora-dialog-locked-height");
      dialog.style.removeProperty("--axora-dialog-keyboard-gap");
      delete dialog.dataset.axoraFixedHeight;
    }
    function ensureFocusVisible(){
      const dialog=openModal(),input=document.activeElement;
      if(!dialog || !input || !dialog.contains(input))return;
      const vv=window.visualViewport;
      const top=vv?.offsetTop||0;
      const visibleBottom=top+(vv?.height||window.innerHeight)-18;
      const focused=input.getBoundingClientRect();
      if(focused.bottom>visibleBottom){
        dialog.scrollTop+=focused.bottom-visibleBottom+12;
      } else if(focused.top<top+12){
        dialog.scrollTop-=top+12-focused.top;
      }
    }
    function updateKeyboardSpace(){
      const dialog=openModal();
      if(!dialog || !mobile())return;
      const input=document.activeElement;
      const editing=Boolean(input && dialog.contains(input) &&
        input.matches("input:not([type=checkbox]):not([type=radio]),select,textarea"));
      const vv=window.visualViewport;
      const hidden=editing && vv ?
        Math.max(0,window.innerHeight-(vv.height+vv.offsetTop)) : 0;
      const gap=hidden>100?Math.ceil(hidden+18):0;
      dialog.style.setProperty("--axora-dialog-keyboard-gap",gap+"px");
      if(editing)window.requestAnimationFrame(ensureFocusVisible);
    }
    for(const dialog of modals){
      const observer=new MutationObserver(()=>{
        if(dialog.open){
          lockDialog(dialog);
          updateKeyboardSpace();
        }else{
          clearDialog(dialog);
        }
      });
      observer.observe(dialog,{attributes:true,attributeFilter:["open"]});
      if(dialog.open)lockDialog(dialog);
    }
    document.addEventListener("focusin",event=>{
      if(event.target.closest?.(selector)){
        window.setTimeout(updateKeyboardSpace,75);
      }
    });
    document.addEventListener("focusout",event=>{
      if(event.target.closest?.(selector)){
        window.setTimeout(updateKeyboardSpace,75);
      }
    });
    if(window.visualViewport){
      window.visualViewport.addEventListener("resize",updateKeyboardSpace,{passive:true});
      window.visualViewport.addEventListener("scroll",updateKeyboardSpace,{passive:true});
    }
    window.addEventListener("resize",()=>{
      if(Math.abs(window.innerWidth-viewportWidth)<3)return;
      viewportWidth=window.innerWidth;
      // Rotação real do dispositivo: a janela mudou de largura, não só altura.
      for(const dialog of modals){
        if(dialog.open){
          clearDialog(dialog);
          window.setTimeout(()=>lockDialog(dialog),330);
        }
      }
    },{passive:true});
  }

  // Durante login e navegação evita recálculo ao alternar exibição da senha.
  // A rolagem interna do login permanece habilitada para acessibilidade.
})();
