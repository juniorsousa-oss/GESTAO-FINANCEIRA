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
  const enabled=bankingData?.provider?.configured;
  return '<div class="notice bank-info"><b>'+(enabled?'MeuPluggy pessoal disponível.':'Conexão bancária ainda não configurada.')+'</b> '+
    (enabled?'Vincule sua conta já autorizada no MeuPluggy. A sincronização consulta saldo e extrato automaticamente, sem movimentar dinheiro.':
    'Os cadastros manuais e a conciliação continuam disponíveis. O administrador pode configurar as credenciais pessoais na VPS.')+
    ' As transações bancárias importadas permanecem pendentes até sua confirmação.</div>';
}
function bankUnavailable(){
  return '<section class="panel"><h2>Dados bancários indisponíveis</h2><p class="panel-copy">'+
   (bankingError?'Confira a migração bancária no Supabase antes de usar o módulo.':'Carregando cadastros...')+'</p></section>';
}
function bankBalancePanel(){
  const b=bankingData?.balances;
  if(!b)return "";
  const holders=bankingData.holders||[], accounts=bankingData.accounts||[];
  const ownKnown=accounts.filter(a=>holders.some(h=>Number(h.id)===Number(a.holder_id)
    && h.relationship==="proprio" && (a.pluggy_account_id?a.pluggy_balance!=null:a.manual_balance!=null))).length;
  const rows=(b.holders||[]).map(h=>
    '<div class="bank-holder-balance"><div><b>'+esc(h.name)+'</b><small>'+
    (h.relationship==="proprio"?"Minhas contas":esc(holderRelations[h.relationship]||"Outro"))+
    ' · '+h.known+' com saldo'+(h.missing?' · '+h.missing+' sem saldo':'')+'</small></div><strong>'+
    (h.known?money(h.total):"Não informado")+'</strong></div>').join("");
  return '<section class="panel bank-balance-panel"><div class="bank-balance-heading"><div>'+
    '<h2>Resumo dos saldos bancários</h2><p>Seu dinheiro separado dos demais titulares.</p></div>'+
    '<span>'+b.known_accounts+' de '+accounts.length+' saldos informados</span></div>'+
    '<div class="bank-balance-grid">'+
    '<div class="bank-balance-metric bank-balance-mine"><span>Meu dinheiro</span><strong>'+
    (ownKnown?money(b.personal):'Não informado')+'</strong><small>'+
    (b.personal_missing?'Parcial · '+b.personal_missing+' conta(s) pendente(s)':'Soma das minhas contas')+'</small></div>'+
    '<div class="bank-balance-metric"><span>Outros titulares</span><strong>'+
    (b.known_accounts>ownKnown?money(b.family):'Não informado')+'</strong><small>'+
    (b.family_missing?'Parcial · '+b.family_missing+' conta(s) pendente(s)':'Contas dos familiares')+'</small></div>'+
    '<div class="bank-balance-metric"><span>Todas as contas</span><strong>'+
    (b.known_accounts?money(b.combined):'Não informado')+'</strong><small>'+
    (b.missing_accounts?'Parcial, há contas sem saldo':'Visão conjunta, não patrimônio individual')+'</small></div></div>'+
    (b.missing_accounts?'<p class="bank-balance-note"><b>Resumo parcial:</b> '+b.missing_accounts+
     ' conta(s) ainda sem saldo informado. Não foram consideradas como saldo zero.</p>':'')+
    '<div class="bank-holder-balances">'+rows+'</div>'+
    '<p class="bank-balance-footnote">Saldos conectados vêm do MeuPluggy; os outros são informados manualmente. Não somamos extratos, lançamentos ou previsões para evitar duplicidades.</p></section>';
}
function bankingAccountsPage(){
  if(!bankingData||bankingError)return bankUnavailable();
  const holders=bankingData.holders||[],accounts=bankingData.accounts||[];
  const people=holders.map(h=>'<div class="bank-entity"><div><strong>'+esc(h.name)+'</strong><small>'+esc(holderRelations[h.relationship]||"Outro")+'</small></div>'+
    '<div class="bank-entity-actions"><button type="button" class="btn ghost small" data-action="bank-edit-holder" data-id="'+Number(h.id)+'">Editar</button>'+
    '<button type="button" class="btn ghost small bank-delete" data-action="bank-delete-holder" data-id="'+Number(h.id)+'">Excluir</button></div></div>').join("");
  const cards=accounts.map(a=>{
    const h=holders.find(x=>Number(x.id)===Number(a.holder_id));
    return '<div class="bank-account-card"><div class="bank-card-top"><span class="bank-icon">'+interfaceIcon("wallet")+'</span><span class="bank-tag">'+(a.pluggy_account_id?'MeuPluggy · leitura':'Manual')+'</span></div>'+
      '<strong>'+esc(a.nickname)+'</strong><div>'+esc(a.bank_name)+' · '+esc(h?.name||"Titular")+'</div>'+
      '<small>'+esc(a.account_type)+' · BRL</small>'+
      (a.pluggy_account_id?
       '<p class="bank-connected">Saldo bancário: '+(a.pluggy_balance==null?'Aguardando consulta':money(a.pluggy_balance))+
       (a.pluggy_last_synced?' · Sincronizado '+esc(a.pluggy_last_synced.slice(0,16).replace("T"," ")):'')+'</p>':
       '<p class="bank-manual-balance">Saldo informado: '+(a.manual_balance==null?'Não informado':money(a.manual_balance))+'</p>')+
      '<div class="bank-account-actions">'+
      (a.pluggy_account_id?
        (bankingData?.provider?.configured?'<button type="button" class="btn primary small" data-action="meu-pluggy-sync" data-id="'+Number(a.id)+'">Sincronizar</button>':''):
        '<button type="button" class="btn primary small" data-action="bank-update-balance" data-id="'+Number(a.id)+'">Atualizar saldo</button>')+
      (bankingData?.provider?.configured && !a.pluggy_account_id && h?.relationship==="proprio"?
        '<button type="button" class="btn ghost small" data-action="meu-pluggy-link" data-id="'+Number(a.id)+'">Vincular MeuPluggy</button>':'')+
      '<button type="button" class="btn ghost small" data-action="bank-edit-account" data-id="'+Number(a.id)+'">Editar</button>'+
      '<button type="button" class="btn ghost small bank-delete" data-action="bank-delete-account" data-id="'+Number(a.id)+'">Excluir</button></div></div>';
  }).join("");
  return '<div class="stack bank-module">'+bankBalancePanel()+bankInfoBanner()+
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
function bankHistoryRow(h){
  const title=h.action==="reversed"?"Conciliação desfeita":(bankingModes[h.action]||h.action);
  return '<div class="bank-history-row"><div class="bank-history-content"><strong>'+esc(title)+'</strong>'+
    '<small>Transação #'+Number(h.transaction_id)+' · usuário #'+Number(h.actor_id)+
    ' · '+esc(h.created_at?.slice(0,16).replace("T"," ")||"")+'</small>'+
    (h.bank_description?'<small>'+esc(h.bank_description)+'</small>':'')+
    (h.action==="reversed"&&h.notes?'<small>Motivo: '+esc(h.notes)+'</small>':'')+'</div>'+
    (h.can_undo?'<button type="button" class="btn ghost small bank-undo-btn" data-action="bank-undo" data-id="'+Number(h.id)+'">Desfazer conciliação</button>':'')+
    '</div>';
}
function bankOpenUndo(eventId){
  const event=(bankingHistory||[]).find(h=>Number(h.id)===Number(eventId));
  if(!event||!event.can_undo)throw Error("Esta conciliação não pode mais ser revertida. Atualize o histórico.");
  const form=$("#bank-undo-form");form.reset();
  form.elements.transaction_id.value=event.transaction_id;
  $("#bank-undo-detail").textContent=
    (event.bank_description||"Transação #"+event.transaction_id)+" · "+(bankingModes[event.action]||event.action);
  $("#bank-undo-dialog").showModal();
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
    '<div id="bank-history-list">'+(bankingHistory?bankingHistory.map(bankHistoryRow).join("")||'<p class="panel-copy">Ainda não há decisões registradas.</p>':'<p class="panel-copy">Clique para carregar o histórico de validações.</p>')+'</div></section></div>';
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
    select.add(new Option((c.learned_count?"Padrão aprendido ("+c.learned_count+") · ":"")+
      c.strength+" proximidade · "+c.label+" · "+money(c.value)+
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
async function bankOpenMeuPluggy(localId){
  const local=(bankingData?.accounts||[]).find(x=>Number(x.id)===Number(localId));
  if(!local)throw Error("Conta não encontrada. Atualize a página.");
  const result=await api("/api/banking/meu-pluggy/accounts");
  const form=$("#meu-pluggy-link-form");
  form.reset();
  form.elements.account_id.value=localId;
  $("#meu-pluggy-local-account").textContent=local.bank_name+" · "+local.nickname;
  bankFillSelect(form.elements.provider_account_id,
    (result.accounts||[]).map(a=>({
      id:a.id,
      label:a.name+(a.last_digits?" · final "+a.last_digits:"")+
        (a.balance!=null?" · Saldo "+money(a.balance):"")
    })), "Selecione sua conta autorizada no MeuPluggy");
  if(!(result.accounts||[]).length)
    throw Error("Nenhuma conta bancária em BRL disponível neste item MeuPluggy.");
  $("#meu-pluggy-link-dialog").showModal();
}
async function bankSyncMeuPluggy(accountId){
  const account=(bankingData?.accounts||[]).find(x=>Number(x.id)===accountId);
  if(!account)throw Error("Conta não encontrada.");
  const result=await api("/api/banking/meu-pluggy/sync/"+accountId,{
    method:"POST",body:"{}"
  });
  await loadBanking(true);
  showToast("Extrato consultado: "+result.checked+" transação(ões) verificadas. Conciliação manual obrigatória.");
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
      else if(action==="meu-pluggy-link")await bankOpenMeuPluggy(Number(el.dataset.id));
      else if(action==="meu-pluggy-sync")await bankSyncMeuPluggy(Number(el.dataset.id));
      else if(action==="bank-new-transaction")bankOpenTransaction();
      else if(action==="bank-analyze")await bankOpenAnalysis(Number(el.dataset.id));
       else if(action==="bank-undo")bankOpenUndo(Number(el.dataset.id));
      else if(action==="bank-review")bankReviewDecision();
      else if(action==="bank-history"){
        const result=await api("/api/banking/history");bankingHistory=result.items||[];render();
      }
    }catch(err){showToast(err.message,true)}
  });
  document.querySelectorAll("[data-bank-dismiss]").forEach(el=>el.addEventListener("click",()=>el.closest("dialog").close()));
  document.querySelectorAll("[data-meu-pluggy-dismiss]").forEach(el=>{
    el.addEventListener("click",()=>$("#meu-pluggy-link-dialog").close());
  });
  $("#meu-pluggy-link-form").addEventListener("submit",async e=>{
    e.preventDefault();
    const form=e.currentTarget,button=form.querySelector('button[type="submit"]');
    button.disabled=true;
    try{
      if(!form.elements.confirm_owner.checked)throw Error("Confirme a titularidade.");
      const data={
        account_id:Number(form.elements.account_id.value),
        provider_account_id:form.elements.provider_account_id.value,
        confirm_owner:true
      };
      await api("/api/banking/meu-pluggy/link",{method:"POST",body:JSON.stringify(data)});
      $("#meu-pluggy-link-dialog").close();
      await loadBanking(true);
      showToast("Conta vinculada. A atualização automática está habilitada.");
    }catch(err){showToast(err.message,true)}
    finally{button.disabled=false}
  });
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
  $("#bank-undo-form").addEventListener("submit",async e=>{
    e.preventDefault();
    const form=e.currentTarget,button=form.querySelector('button[type="submit"]');
    button.disabled=true;
    const payload={transaction_id:Number(form.elements.transaction_id.value),
                   reason:form.elements.reason.value.trim()};
    try{
      await api("/api/banking/reconcile/undo",{method:"POST",body:JSON.stringify(payload)});
      $("#bank-undo-dialog").close();bankingHistory=null;
      await refresh();await loadBanking(true);
      const history=await api("/api/banking/history");
      bankingHistory=history.items||[];render();
      showToast("Conciliação desfeita. A transação voltou à fila para nova análise.");
    }catch(err){showToast(err.message,true)}
    finally{button.disabled=false}
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
