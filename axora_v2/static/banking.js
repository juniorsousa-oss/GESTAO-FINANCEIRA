/* AXORA | Contas manuais e conciliação de transações.
   Nesta fase, os dados são informados pelo usuário, não vêm do Open Finance.
   Nenhuma sugestão modifica Registros sem a conferência e confirmação final. */
"use strict";
let bankingData=null,bankingError=null,bankingRequest=null,bankingHistory=null;
let bankingSelected=null,bankingCandidates=[],bankingChoice=null,bankingReview=false;
const bankingModes={matched_record:"Vincular Registro existente",matched_provision:"Quitar Provisão",recorded:"Criar Registro",transfer:"Transferência interna",ignored:"Ignorar movimentação"};
const holderRelations={proprio:"Próprio",conjuge:"Cônjuge",mae:"Mãe",pai:"Pai",familiar:"Familiar",outro:"Outro"};

async function loadBanking(force=false){
  if(bankingRequest)return bankingRequest;
  if(!force&&bankingData)return bankingData;
  bankingRequest=(async()=>{
    try{
      const data=await api("/api/banking");
      bankingData=data;bankingError=null;
      if(page==="bank-accounts"||page==="reconciliation")render();
      return data;
    }catch(e){
      bankingError=e.message;
      if(page==="bank-accounts"||page==="reconciliation")render();
      throw e;
    }finally{bankingRequest=null}
  })();
  return bankingRequest;
}
function bankTitle(item){
  const account=(bankingData?.accounts||[]).find(x=>Number(x.id)===Number(item.account_id));
  const holder=(bankingData?.holders||[]).find(x=>Number(x.id)===Number(account?.holder_id));
  return (account?.bank_name||"Banco")+" · "+(account?.nickname||"Conta")+
    " · "+(holder?.name||"Titular");
}
function bankInfoBanner(){
  return '<div class="notice bank-info"><b>Modo manual — sem conexão bancária.</b> Cadastre titulares, contas e transações de exemplo. Nenhuma consulta à CAIXA, Nubank ou outro banco está ativa. Somente dados validados entram nos Registros.</div>';
}
function bankUnavailable(){
  return '<section class="panel"><h2>Dados bancários indisponíveis</h2><p class="panel-copy">'+
   (bankingError?'Confira a migração bancária no Supabase antes de usar o módulo.':'Carregando cadastros...')+'</p></section>';
}
function bankingAccountsPage(){
  if(!bankingData||bankingError)return bankUnavailable();
  const holders=bankingData.holders||[],accounts=bankingData.accounts||[];
  const people=holders.map(h=>'<div class="bank-entity"><div><strong>'+esc(h.name)+'</strong><small>'+esc(holderRelations[h.relationship]||"Outro")+'</small></div>'+
    '<div class="bank-entity-actions"><button type="button" class="btn ghost small" data-action="bank-edit-holder" data-id="'+Number(h.id)+'">Editar</button>'+
    '<button type="button" class="btn ghost small bank-delete" data-action="bank-delete-holder" data-id="'+Number(h.id)+'">Excluir</button></div></div>').join("");
  const cards=accounts.map(a=>{
    const h=holders.find(x=>Number(x.id)===Number(a.holder_id));
    return '<div class="bank-account-card"><div class="bank-card-top"><span class="bank-icon">'+interfaceIcon("wallet")+'</span><span class="bank-tag">Manual</span></div>'+
      '<strong>'+esc(a.nickname)+'</strong><div>'+esc(a.bank_name)+' · '+esc(h?.name||"Titular")+'</div>'+
      '<small>'+esc(a.account_type)+' · BRL</small><p>Sem sincronização bancária</p>'+
      '<div class="bank-account-actions"><button type="button" class="btn ghost small" data-action="bank-edit-account" data-id="'+Number(a.id)+'">Editar</button>'+
      '<button type="button" class="btn ghost small bank-delete" data-action="bank-delete-account" data-id="'+Number(a.id)+'">Excluir</button></div></div>';
  }).join("");
  return '<div class="stack bank-module">'+bankInfoBanner()+
    panel("Contas cadastradas","Cada conta é individual, mesmo quando o banco é o mesmo.",
       '<div class="bank-cards">'+(cards||'<p class="panel-copy">Cadastre uma conta para começar.</p>')+'</div>')+
    panel("Titulares","Diferencie os responsáveis. O acesso familiar compartilhado será configurado em uma próxima etapa.",
      '<div class="bank-entities">'+(people||'<p class="panel-copy">Nenhum titular cadastrado.</p>')+'</div>')+
    '</div>';
}
function bankTransactionRow(tx){
  return '<div class="bank-transaction"><div class="bank-transaction-main">'+
      '<div class="bank-transaction-date">'+dateBR(tx.posted_on)+'</div>'+
      '<div><strong>'+esc(tx.description)+'</strong><small>'+esc(bankTitle(tx))+'</small></div></div>'+
      '<div class="bank-transaction-actions"><strong class="'+(Number(tx.amount)<0?'bank-negative':'bank-positive')+'">'+
      money(tx.amount)+'</strong><button class="btn primary small" type="button" data-action="bank-analyze" data-id="'+Number(tx.id)+'">Analisar</button></div></div>';
}
function bankingReconciliationPage(){
  if(!bankingData||bankingError)return bankUnavailable();
  const pending=bankingData.pending||[];
  return '<div class="stack bank-module">'+bankInfoBanner()+
    '<div class="metric-grid">'+
    '<div class="metric-card"><div class="metric-label">Não conciliadas</div><div class="metric-value">'+pending.length+'</div><div class="metric-meta">Aguardam decisão do operador</div></div>'+
    '<div class="metric-card"><div class="metric-label">Saídas pendentes</div><div class="metric-value">'+money(pending.filter(t=>Number(t.amount)<0).reduce((sum,t)=>sum+Math.abs(Number(t.amount)),0))+'</div><div class="metric-meta">Não lançadas automaticamente</div></div>'+
    '<div class="metric-card"><div class="metric-label">Entradas pendentes</div><div class="metric-value">'+money(pending.filter(t=>Number(t.amount)>0).reduce((sum,t)=>sum+Number(t.amount),0))+'</div><div class="metric-meta">Aguardam validação</div></div></div>'+
    panel("Movimentações aguardando análise","A fila mostra apenas transações ainda não conciliadas. Selecione uma para consultar sugestões.",
      '<div class="bank-transaction-list">'+(pending.map(bankTransactionRow).join("")||
      '<div class="empty-state"><b>Nenhuma transação pendente.</b> Cadastre uma transação manual para testar a conciliação.</div>')+'</div>')+
    '<section class="panel"><div class="bank-history-heading"><div><h2>Histórico de decisões</h2><p>Quem confirmou, qual ação foi tomada e quando.</p></div>'+
    '<button type="button" class="btn ghost small" data-action="bank-history">Consultar histórico</button></div>'+
    '<div id="bank-history-list">'+(bankingHistory?bankingHistory.map(h=>'<div class="bank-history-row"><strong>'+esc(bankingModes[h.action]||h.action)+'</strong><small>Transação #'+Number(h.transaction_id)+' · usuário #'+Number(h.actor_id)+' · '+esc(h.created_at?.slice(0,16).replace("T"," ")||"")+'</small></div>').join("")||'<p class="panel-copy">Ainda não há decisões registradas.</p>':'<p class="panel-copy">Clique para carregar o histórico de validações.</p>')+'</div></section></div>';
}
function bankFillSelect(select,items,label){
  select.replaceChildren(new Option(label,""));
  for(const item of items)select.add(new Option(item.label,item.id));
}
function bankOpenHolder(id=null){
  const form=$("#bank-holder-form");form.reset();
  const selected=id===null?null:(bankingData?.holders||[]).find(h=>Number(h.id)===Number(id));
  if(id!==null&&!selected)throw Error("Titular não localizado. Atualize a lista.");
  form.elements.record_id.value=selected?.id||"";
  if(selected){
    form.elements.name.value=selected.name;
    form.elements.relationship.value=selected.relationship;
  }
  $("#bank-holder-title").textContent=selected?"Editar titular":"Novo titular";
  $("#bank-holder-submit").textContent=selected?"Salvar alterações":"Salvar titular";
  $("#bank-holder-dialog").showModal();
}
function bankOpenAccount(id=null){
  if(!(bankingData?.holders||[]).length){showToast("Cadastre primeiro um titular.",true);return}
  const form=$("#bank-account-form");form.reset();
  const selected=id===null?null:(bankingData?.accounts||[]).find(a=>Number(a.id)===Number(id));
  if(id!==null&&!selected)throw Error("Conta não localizada. Atualize a lista.");
  form.elements.record_id.value=selected?.id||"";
  bankFillSelect(form.elements.holder_id,bankingData.holders.map(h=>({id:h.id,label:h.name})),
                 "Selecione o titular");
  if(selected){
    form.elements.holder_id.value=selected.holder_id;
    form.elements.bank_name.value=selected.bank_name;
    form.elements.nickname.value=selected.nickname;
    form.elements.account_type.value=selected.account_type;
  }
  $("#bank-account-title").textContent=selected?"Editar conta bancária":"Nova conta bancária";
  $("#bank-account-submit").textContent=selected?"Salvar alterações":"Salvar conta";
  $("#bank-account-dialog").showModal();
}
function bankOpenTransaction(){
  if(!(bankingData?.accounts||[]).length){showToast("Cadastre primeiro uma conta bancária.",true);return}
  const form=$("#bank-transaction-form");form.reset();
  bankFillSelect(form.elements.account_id,bankingData.accounts.map(a=>({id:a.id,label:a.bank_name+" · "+a.nickname})),
                 "Selecione a conta");
  form.elements.posted_on.value=provisionToday();
  $("#bank-transaction-dialog").showModal();
}
async function bankOpenAnalysis(id){
  const tx=(bankingData?.pending||[]).find(x=>Number(x.id)===Number(id));
  if(!tx)throw Error("A transação já saiu da fila. Atualize.");
  bankingSelected=tx;bankingChoice=null;bankingReview=false;
  const response=await api("/api/banking/transactions/"+tx.id+"/suggestions");
  bankingCandidates=response.candidates||[];
  const form=$("#bank-decision-form");form.reset();
  form.elements.transaction_id.value=tx.id;
  $("#bank-decision-detail").textContent=tx.description+" · "+money(tx.amount)+" · "+bankTitle(tx);
  const select=form.elements.action_choice;
  select.replaceChildren(new Option("Selecione a decisão do operador",""));
  for(const c of bankingCandidates){
    select.add(new Option(c.strength+" proximidade · "+c.label+" · "+money(c.value)+
      " · "+dateBR(c.date)+(c.can_confirm?"":" (valor diferente: revisão necessária)"),c.kind+":"+c.id));
  }
  const transfers=(bankingData.pending||[]).filter(x=>x.id!==tx.id&&x.account_id!==tx.account_id
    &&Math.abs(Number(x.amount)+Number(tx.amount))<.011);
  for(const x of transfers)select.add(new Option("Transferência · "+bankTitle(x)+" · "+dateBR(x.posted_on),
                                      "transfer:"+x.id));
  select.add(new Option("Criar novo Registro","recorded"));
  select.add(new Option("Ignorar (com justificativa)","ignored"));
  bankDecisionState();
  $("#bank-decision-dialog").showModal();
}
function bankDecisionState(){
  const f=$("#bank-decision-form"),choice=f.elements.action_choice.value;
  const [kind,target]=choice.includes(":")?choice.split(":"):[choice,""];
  bankingChoice={kind,target:Number(target)||null};
  bankingReview=false;
  const match=bankingCandidates.find(x=>x.kind===kind&&Number(x.id)===Number(target));
  $("#bank-decision-reasons").textContent=match?
     ("Motivos sugeridos: "+match.reasons.join(", ")+(match.can_confirm?"":". Os valores diferem: esta opção não pode ser confirmada nesta fase.")):
     "Nenhuma classificação será aplicada automaticamente.";
  $("#bank-category-wrap").hidden=kind!=="recorded";
  $("#bank-ignore-wrap").hidden=kind!=="ignored";
  f.elements.category.required=kind==="recorded";
  f.elements.reason.required=kind==="ignored";
  $("#bank-review-summary").hidden=true;
  $("#bank-review-button").disabled=!kind||Boolean(match&&!match.can_confirm);
  $("#bank-submit").disabled=true;
  if(kind==="recorded") {
    const active=(financeCatalogItems||[]).filter(x=>x.kind==="category"&&x.active);
    bankFillSelect(f.elements.category,active.map(x=>({id:x.name,label:x.name})),
                   "Selecione uma categoria");
  }
}
function bankReviewDecision(){
  const f=$("#bank-decision-form"),c=bankingChoice;
  if(!c||!c.kind)throw Error("Escolha primeiro uma decisão.");
  if(c.kind==="recorded"&&!f.elements.category.value)throw Error("Informe a categoria.");
  if(c.kind==="ignored"&&f.elements.reason.value.trim().length<5)throw Error("Justifique o descarte.");
  const match=bankingCandidates.find(x=>x.kind===c.kind&&x.id===c.target);
  if(match&&!match.can_confirm)throw Error("O valor diverge. Ajustes e pagamentos parciais virão em outra etapa.");
  bankingReview=true;
  $("#bank-review-summary").hidden=false;
  $("#bank-review-summary").textContent="Conferência final: "+bankingModes[c.kind]+
    " · "+bankingSelected.description+" · "+money(bankingSelected.amount)+
    (match?" · "+match.label:"")+". Esta ação só será gravada após clicar em Confirmar decisão.";
  $("#bank-submit").disabled=false;
}
async function bankSaveForm(form,endpoint,transform=x=>x){
  const button=form.querySelector('button[type="submit"]');button.disabled=true;
  try{
    const raw=Object.fromEntries(new FormData(form).entries());
    const id=raw.record_id||"";
    delete raw.record_id;
    const data=transform(raw);
    await api(endpoint+(id?"/"+Number(id):""),{
      method:id?"PATCH":"POST",body:JSON.stringify(data)
    });
    form.closest("dialog").close();
    await loadBanking(true);
    showToast(id?"Cadastro atualizado com sucesso.":"Cadastro adicionado com sucesso.");
  }catch(e){showToast(e.message,true)}
  finally{button.disabled=false}
}
async function bankDelete(type,id){
  const holder=type==="holder";
  const collection=holder?bankingData?.holders:bankingData?.accounts;
  const item=(collection||[]).find(x=>Number(x.id)===Number(id));
  if(!item)throw Error("Cadastro não localizado. Atualize a lista.");
  const label=holder?item.name:item.nickname;
  if(holder&&(bankingData?.accounts||[]).some(a=>Number(a.holder_id)===Number(id))){
    throw Error("Este titular possui contas vinculadas. Exclua primeiro as contas sem movimentações ou edite o titular.");
  }
  // A API revalida todas as relações; a confirmação não substitui a proteção do banco.
  if(!confirm("Excluir "+(holder?"o titular":"a conta")+" \""+label+"\"? Esta ação só é permitida quando não há vínculos financeiros."))return;
  const endpoint=holder?"/api/banking/holders/":"/api/banking/accounts/";
  await api(endpoint+Number(id),{method:"DELETE"});
  await loadBanking(true);
  showToast(holder?"Titular excluído.":"Conta bancária excluída.");
}
document.addEventListener("DOMContentLoaded",()=>{
  document.addEventListener("click",async e=>{
    const el=e.target.closest("[data-action]");if(!el)return;
    const action=el.dataset.action;
    try{
      if(action==="bank-new-holder")bankOpenHolder();
      else if(action==="bank-new-account")bankOpenAccount();
      else if(action==="bank-edit-holder")bankOpenHolder(Number(el.dataset.id));
      else if(action==="bank-edit-account")bankOpenAccount(Number(el.dataset.id));
      else if(action==="bank-delete-holder")await bankDelete("holder",Number(el.dataset.id));
      else if(action==="bank-delete-account")await bankDelete("account",Number(el.dataset.id));
      else if(action==="bank-new-transaction")bankOpenTransaction();
      else if(action==="bank-analyze")await bankOpenAnalysis(Number(el.dataset.id));
      else if(action==="bank-review")bankReviewDecision();
      else if(action==="bank-history"){
        const result=await api("/api/banking/history");bankingHistory=result.items||[];render();
      }
    }catch(err){showToast(err.message,true)}
  });
  document.querySelectorAll("[data-bank-dismiss]").forEach(el=>el.addEventListener("click",()=>el.closest("dialog").close()));
  $("#bank-holder-form").addEventListener("submit",e=>{
    e.preventDefault();bankSaveForm(e.currentTarget,"/api/banking/holders");
  });
  $("#bank-account-form").addEventListener("submit",e=>{
    e.preventDefault();bankSaveForm(e.currentTarget,"/api/banking/accounts",
     x=>({...x,holder_id:Number(x.holder_id)}));
  });
  $("#bank-transaction-form").addEventListener("submit",e=>{
    e.preventDefault();bankSaveForm(e.currentTarget,"/api/banking/transactions",
     x=>({...x,account_id:Number(x.account_id),amount:Number(x.amount)}));
  });
  $("#bank-decision-form").elements.action_choice.addEventListener("change",bankDecisionState);
  $("#bank-decision-form").addEventListener("submit",async e=>{
    e.preventDefault();
    if(!bankingReview||!bankingChoice)return;
    const f=e.currentTarget,button=$("#bank-submit");button.disabled=true;
    const c=bankingChoice;
    const payload={transaction_id:bankingSelected.id,action:c.kind};
    if(c.kind==="matched_record"||c.kind==="matched_provision")payload.target_id=c.target;
    if(c.kind==="transfer")payload.counterpart_id=c.target;
    if(c.kind==="recorded")payload.category=f.elements.category.value;
    if(c.kind==="ignored")payload.reason=f.elements.reason.value.trim();
    try{
      await api("/api/banking/reconcile",{method:"POST",body:JSON.stringify(payload)});
      $("#bank-decision-dialog").close();
      bankingSelected=null;bankingReview=false;bankingHistory=null;
      await refresh();await loadBanking(true);
      showToast("Decisão confirmada e registrada no histórico.");
    }catch(err){showToast(err.message,true);button.disabled=false}
  });
});
