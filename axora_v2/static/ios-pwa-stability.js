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

  // Durante login e navegação evita recálculo ao alternar exibição da senha.
  // A rolagem interna do login permanece habilitada para acessibilidade.
})();
