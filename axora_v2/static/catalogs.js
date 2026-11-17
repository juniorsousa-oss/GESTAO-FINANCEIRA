/* AXORA | Catálogos financeiros por espaço: categorias e responsáveis. */
"use strict";
let financeCatalogItems=null;
let financeCatalogPending=null;
let financeCatalogError=null;

function resetFinancialCatalogs(){
  financeCatalogItems=null;
  financeCatalogPending=null;
  financeCatalogError=null;
}
async function loadFinanceCatalogs(force=false){
  if(!force && financeCatalogItems!==null)return financeCatalogItems;
  if(financeCatalogPending)return financeCatalogPending;
  financeCatalogPending=(async()=>{
    try{
      const result=await api("/api/catalogs");
      financeCatalogItems=Array.isArray(result.items)?result.items:[];
      financeCatalogError=null;
      if(page==="settings")render();
      return financeCatalogItems;
    }catch(e){
      financeCatalogError=e.message;
      if(page==="settings")render();
      throw e;
    }finally{financeCatalogPending=null}
  })();
  return financeCatalogPending;
}
function catalogGroup(kind){
  const heading=kind==="category"?"Categorias":"Responsáveis anteriores";
  const items=(financeCatalogItems||[]).filter(it=>it.kind===kind)
       .sort((a,b)=>Number(b.active)-Number(a.active)||a.name.localeCompare(b.name,"pt-BR"));
  const rows=items.map(item=>'<div class="catalog-option'+(item.active?'':' catalog-inactive')+'">'+
      '<div class="catalog-option-label"><b>'+esc(item.name)+'</b><span>'+(item.active?'Ativo':'Inativo')+'</span></div>'+
      '<button type="button" class="btn ghost small" data-action="catalog-toggle" data-catalog-id="'+Number(item.id)+'" data-catalog-active="'+(item.active?"false":"true")+'" aria-label="'+(item.active?"Desativar ":"Reativar ")+esc(item.name)+'">'+(item.active?'Desativar':'Reativar')+'</button></div>').join("");
  return '<section class="catalog-group"><div class="catalog-group-head"><h3>'+heading+'</h3><span>'+items.filter(it=>it.active).length+' ativo(s)</span></div>'+
    '<div class="catalog-option-list">'+(rows||'<p class="panel-copy">Nenhuma opção cadastrada.</p>')+'</div>'+
    (kind==="category"?'<form class="catalog-create-form" data-catalog-kind="category"><label for="catalog-add-category">Adicionar categoria</label>'+
    '<div class="catalog-create-row"><input id="catalog-add-category" name="name" type="text" maxlength="120" autocomplete="off" placeholder="Ex.: Moradia, Saúde" required>'+
    '<button class="btn primary small" type="submit">Adicionar</button></div></form>':
    '<p class="panel-copy">Para adicionar pessoas, use <b>Titulares cadastrados</b> nesta página. '+
    'Estes nomes antigos permanecem apenas para compatibilidade com lançamentos existentes.</p>')+'</section>';
}
function financialCatalogPanel(){
  if(financeCatalogError)return '<div class="notice warning">Não foi possível carregar os catálogos. Verifique a atualização do banco.<div class="page-actions"><button class="btn ghost small" type="button" data-action="catalog-retry">Tentar novamente</button></div></div>';
  if(financeCatalogItems===null)return '<p class="panel-copy">Carregando categorias e responsáveis…</p>';
  return '<div class="financial-catalogs"><p class="panel-copy">Categorias continuam neste painel. '+
    'Pessoas são administradas em Titulares cadastrados; os responsáveis históricos permanecem disponíveis sem duplicar o cadastro.</p>'+
    '<div class="catalog-grid">'+catalogGroup("category")+catalogGroup("responsible")+'</div>'+
    '<div class="catalog-export-area"><p class="panel-copy">Baixe a relação com nomes padronizados, situação e instruções. O CSV abre no Excel e pode ser compartilhado como referência com a equipe.</p>'+
    '<button class="btn ghost" type="button" data-action="catalog-export">'+interfaceIcon("download")+' Exportar listas (CSV)</button></div></div>';
}
function hydrateProvisionCatalogs(selector="#provision-form"){
  const form=document.querySelector(selector);
  if(!form||!Array.isArray(financeCatalogItems))return;
  for(const [field,kind,title] of [
    ["category","category","Selecione uma categoria"],
    ["responsible","responsible","Selecione um responsável"]
  ]){
    const select=form.elements[field];
    if(!select)return;
    const previous=select.value;
    select.replaceChildren(new Option(title,""));
    let items=financeCatalogItems.filter(item=>item.kind===kind&&item.active)
      .map(item=>item.name);
    if(kind==="responsible"&&me?.family_enabled&&me?.family_role==="principal"){
      // Um único cadastro de membros; o alias histórico "Próprio" não é
      // uma pessoa e nunca deve aparecer como novo responsável.
      const members=window.AxoraFamily?.profiles?.()||[];
      items=members.filter(p=>p.active).map(p=>p.display_name);
    }else if(kind==="responsible"&&typeof bankingHolderOptions==="function"&&
       (!me?.family_enabled||me.family_role==="principal")){
      for(const holder of bankingHolderOptions())items.push(holder.name);
    }
    const unique=[...new Map(items.map(name=>[String(name).trim().toLocaleLowerCase("pt-BR"),name])).values()]
      .sort((a,b)=>a.localeCompare(b,"pt-BR"));
    for(const name of unique)select.add(new Option(name,name));
    if(unique.some(name=>name===previous))select.value=previous;
  }
}
async function exportFinancialCatalogs(){
  const result=await api("/api/catalogs/export");
  const blob=await result.blob();
  const url=URL.createObjectURL(blob);
  const link=document.createElement("a");
  link.href=url;link.download="axora_categorias_responsaveis.csv";
  document.body.appendChild(link);link.click();link.remove();
  setTimeout(()=>URL.revokeObjectURL(url),3000);
  showToast("Lista de padronização exportada.");
}
document.addEventListener("DOMContentLoaded",()=>{
  document.addEventListener("click",async e=>{
    const control=e.target.closest("[data-action]");
    if(!control)return;
    const action=control.dataset.action;
    if(!["catalog-toggle","catalog-export","catalog-retry","open-catalog-settings"].includes(action))return;
    if(action==="open-catalog-settings"){
      document.querySelector("#provision-dialog")?.close();
      go("settings");
      return;
    }
    control.disabled=true;
    try{
      if(action==="catalog-retry"){await loadFinanceCatalogs(true);return}
      if(action==="catalog-export"){await exportFinancialCatalogs();return}
      if(action==="catalog-toggle"){
        const target=Number(control.dataset.catalogId);
        const active=control.dataset.catalogActive==="true";
        if(!active && !confirm("Desativar esta opção? Os lançamentos existentes serão preservados."))return;
        await api("/api/catalogs/"+target,{
          method:"PATCH",body:JSON.stringify({active})
        });
        await loadFinanceCatalogs(true);
        showToast(active?"Opção reativada.":"Opção desativada.");
      }
    }catch(err){showToast(err.message,true)}
    finally{control.disabled=false}
  });
  document.querySelector("#page-content").addEventListener("submit",async e=>{
    const form=e.target.closest(".catalog-create-form");
    if(!form)return;
    e.preventDefault();
    const button=form.querySelector('button[type="submit"]');
    button.disabled=true;
    try{
      const kind=form.dataset.catalogKind,name=form.elements.name.value;
      await api("/api/catalogs",{method:"POST",body:JSON.stringify({kind,name})});
      await loadFinanceCatalogs(true);
      showToast("Nova opção adicionada ao catálogo.");
    }catch(err){showToast(err.message,true)}
    finally{button.disabled=false}
  });
});
