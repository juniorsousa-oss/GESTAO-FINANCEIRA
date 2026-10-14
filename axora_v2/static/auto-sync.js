/* AXORA · Sincronização automática sem interromper o operador.
   Reconsulta dados a cada 45s, no retorno à aba e ao entrar no Dashboard.
   Somente leitura; sem reabrir modais ou recriar a página quando nada mudou. */
"use strict";
const AXORA_SYNC_INTERVAL=45000;
const AXORA_SYNC_MIN_GAP=12000;
let axoraSyncBusy=false;
let axoraLastAutoSync=0;
function axoraCanAutoSync(){
  if(!me || document.visibilityState==="hidden" || axoraSyncBusy)return false;
  if(document.querySelector("dialog[open]"))return false;
  const element=document.activeElement;
  // Preserva filtros, campos e dados digitados em Configurações/Registros.
  if(element && element.matches?.("input:not([type=button]),textarea,select,[contenteditable=true]"))return false;
  return true;
}
async function autoSyncNow(reason="timer"){
  if(!axoraCanAutoSync())return;
  const now=Date.now();
  if(now-axoraLastAutoSync<AXORA_SYNC_MIN_GAP)return;
  axoraSyncBusy=true;
  axoraLastAutoSync=now;
  try{
    await refresh({silent:true});
    if(page==="provisions" && me)await loadProvisions({silent:true});
  }catch{
    // refresh() atualiza o indicador de falha; não exibe pop-ups intrusivos.
  }finally{
    axoraSyncBusy=false;
  }
}
document.addEventListener("DOMContentLoaded",()=>{
  window.setInterval(()=>{autoSyncNow("timer")},AXORA_SYNC_INTERVAL);
  document.addEventListener("visibilitychange",()=>{
    if(document.visibilityState==="visible")autoSyncNow("visibility");
  });
  window.addEventListener("focus",()=>{autoSyncNow("focus")});
});
