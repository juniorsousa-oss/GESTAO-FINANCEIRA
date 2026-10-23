/* AXORA: Provisões (MVP de validação).
   Somente pendentes nesta tela. Pagamento completo vira Registro via RPC atômica.
   Sem reset da base, sem débito direto de contas e sem efeitos sobre a V1. */
"use strict";
let provisionItems=null;
let provisionError=null;
let provisionView="all";
const provisionFilters={search:"",category:"",responsible:"",from:"",to:""};
const provisionNorm=v=>String(v||"").normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLowerCase().trim();
const provisionSixMonthEnd=today=>{
  const d=new Date(today+"T12:00:00"),day=d.getDate();
  d.setDate(1);d.setMonth(d.getMonth()+6);
  d.setDate(Math.min(day,new Date(d.getFullYear(),d.getMonth()+1,0).getDate()));
  return [d.getFullYear(),String(d.getMonth()+1).padStart(2,"0"),String(d.getDate()).padStart(2,"0")].join("-");
};
const provisionRecurrence={once:"Única",unlimited:"Indeterminada",until_date:"Prazo definido",installments:"Parcelada"};
const provisionFrequency={weekly:"Semanal",biweekly:"Quinzenal",monthly:"Mensal",bimonthly:"Bimestral",quarterly:"Trimestral",semiannual:"Semestral",yearly:"Anual"};
const provisionMonth=v=>String(v||"").slice(0,7);
const provisionToday=()=>{const d=new Date();return [d.getFullYear(),String(d.getMonth()+1).padStart(2,"0"),String(d.getDate()).padStart(2,"0")].join("-")};
const provisionSum=items=>items.reduce((total,item)=>total+Number(item.planned_value||0),0);

function provisionsPage(){
  if(provisionError)return '<section class="panel"><h2>Provisões ainda não disponíveis</h2><p class="panel-copy">A migração de banco desta etapa precisa ser aplicada no ambiente de testes antes do cadastro. Os dados antigos permanecem preservados.</p></section>';
  if(provisionItems===null)return '<div class="panel"><p class="panel-copy">Carregando provisões…</p></div>';
  const todayISO=provisionToday(),month=todayISO.slice(0,7);
  const items=provisionItems;
  const overdue=items.filter(x=>x.due_date<todayISO);
  const thisMonth=items.filter(x=>provisionMonth(x.due_date)===month);
  const thirtyDays=new Date(todayISO+"T12:00:00");thirtyDays.setDate(thirtyDays.getDate()+30);
  const limit=[thirtyDays.getFullYear(),String(thirtyDays.getMonth()+1).padStart(2,"0"),String(thirtyDays.getDate()).padStart(2,"0")].join("-");
  const soon=items.filter(x=>x.due_date>=todayISO&&x.due_date<=limit);
  const sixMonthLimit=provisionSixMonthEnd(todayISO);
  const reserve=items.filter(x=>x.due_date>=todayISO&&x.due_date<=sixMonthLimit);
  const categories=[...new Set(items.map(x=>x.category_override||x.rule?.category||"").filter(Boolean))].sort();
  const responsibles=[...new Set(items.map(x=>x.responsible_override||x.rule?.responsible||"").filter(Boolean))].sort();
  const shown=items.filter(x=>{
    if(provisionView==="overdue"&&x.due_date>=todayISO)return false;
    if(provisionView==="month"&&provisionMonth(x.due_date)!==month)return false;
    if(provisionView==="soon"&&(x.due_date<todayISO||x.due_date>limit))return false;
    if(provisionView==="six"&&(x.due_date<todayISO||x.due_date>sixMonthLimit))return false;
    const description=x.description_override||x.rule?.description||"";
    const category=x.category_override||x.rule?.category||"";
    const responsible=x.responsible_override||x.rule?.responsible||"";
    if(provisionFilters.category&&category!==provisionFilters.category)return false;
    if(provisionFilters.responsible&&responsible!==provisionFilters.responsible)return false;
    if(provisionFilters.from&&x.due_date<provisionFilters.from)return false;
    if(provisionFilters.to&&x.due_date>provisionFilters.to)return false;
    if(provisionFilters.search&&!provisionNorm([description,category,responsible].join(" ")).includes(provisionNorm(provisionFilters.search)))return false;
    return true;
  });
  const cards='<div class="metric-grid">'+[
     ["Total comprometido",provisionSum(items),items.length+" ocorrência(s) pendente(s)"],
     ["A vencer no mês",provisionSum(thisMonth),thisMonth.length+" ocorrência(s)"],
     ["Vencidas",provisionSum(overdue),overdue.length+" ocorrência(s) pendente(s)"],
     ["Próximos 30 dias",provisionSum(soon),soon.length+" ocorrência(s)"],
     ["Reserva · 6 meses",provisionSum(reserve),reserve.length+" ocorrência(s) a vencer"]
   ].map(([label,total,note])=>'<div class="metric-card"><div class="metric-label">'+label+'</div><div class="metric-value">'+money(total)+'</div><div class="metric-meta">'+note+'</div></div>').join("")+'</div>';
  const info='<div class="notice">Compromissos sem prazo final continuam ativos: o sistema gera vencimentos em uma <b>janela móvel de 18 meses</b>. A última data exibida não é uma data de encerramento. O indicador <b>Reserva · 6 meses</b> considera somente os próximos seis meses, sem os vencidos. Ao quitar, confira antes se já existe um lançamento para evitar duplicidade.</div>';
  const filterOptions=(options,current,placeholder)=>'<option value="">'+placeholder+'</option>'+
    options.map(x=>'<option value="'+esc(x)+'" '+(current===x?'selected':'')+'>'+esc(x)+'</option>').join("");
  const selector='<div class="provision-filters" aria-label="Filtros de compromissos">'+
    '<label class="provision-filter-label">Período<select id="provision-filter"><option value="all" '+(provisionView==="all"?"selected":"")+'>Todas as pendentes</option><option value="month" '+(provisionView==="month"?"selected":"")+'>Vencimentos do mês</option><option value="overdue" '+(provisionView==="overdue"?"selected":"")+'>Vencidas</option><option value="soon" '+(provisionView==="soon"?"selected":"")+'>Próximos 30 dias</option><option value="six" '+(provisionView==="six"?"selected":"")+'>Próximos 6 meses</option></select></label>'+
    '<label class="provision-filter-label">Categoria<select id="provision-category-filter">'+filterOptions(categories,provisionFilters.category,"Todas")+'</select></label>'+
    '<label class="provision-filter-label">Responsável<select id="provision-responsible-filter">'+filterOptions(responsibles,provisionFilters.responsible,"Todos")+'</select></label>'+
    '<label class="provision-filter-label">De<input type="date" id="provision-from-filter" value="'+esc(provisionFilters.from)+'"></label>'+
    '<label class="provision-filter-label">Até<input type="date" id="provision-to-filter" value="'+esc(provisionFilters.to)+'"></label>'+
    '<label class="provision-filter-label provision-filter-search">Buscar<input type="search" id="provision-search-filter" maxlength="100" value="'+esc(provisionFilters.search)+'" placeholder="Descrição, categoria ou responsável"></label>'+
    '<button class="btn ghost small provision-clear-filters" type="button" data-action="clear-provision-filters">Limpar</button></div>';
  const lines=shown.map(item=>{
    const rule=item.rule||{},late=item.due_date<todayISO;
    const type=provisionRecurrence[rule.recurrence]||"Recorrência";
    const frequency=rule.recurrence==="once"?"":(" · "+(provisionFrequency[rule.frequency]||""));
    const sequence=(rule.recurrence==="installments"||rule.recurrence==="until_date")?
      (" · Vencimento "+item.sequence_no+(rule.installment_count?"/"+rule.installment_count:"")):"";
    const id=Number(item.id),description=item.description_override||rule.description||"";
    const category=item.category_override||rule.category||"";
    const responsible=item.responsible_override||rule.responsible||"";
    const mode=item.value_mode_override||rule.value_mode;
    return '<tr data-provision-search="'+esc(provisionNorm([description,category,responsible].join(" ")))+'"><td data-label="Vencimento"><strong>'+dateBR(item.due_date)+'</strong>'+(late?'<span class="status-badge red">Vencida</span>':'')+'</td>'+
      '<td data-label="Descrição"><strong>'+esc(description)+'</strong><small>'+esc(type+frequency+sequence)+'</small></td>'+
      '<td data-label="Categoria / Responsável">'+esc(category)+'<small>'+esc(responsible)+'</small></td>'+
      '<td data-label="Previsto"><strong>'+money(item.planned_value)+'</strong><small>'+(mode==="fixed"?"Valor fixo":"Valor estimado")+'</small></td>'+
      '<td data-label="Ação"><div class="provision-row-actions"><button type="button" class="btn primary small" data-action="pay-provision" data-id="'+id+'">Registrar pagamento</button>'+
      '<button type="button" class="btn ghost small" data-action="edit-provision" data-id="'+id+'">Editar</button>'+
      '<button type="button" class="btn ghost small provision-delete" data-action="cancel-provision" data-id="'+id+'">Excluir</button></div></td></tr>';
  }).join("");
  const listing=lines?'<div class="provision-scroll"><table class="provision-table"><thead><tr><th>Vencimento</th><th>Descrição</th><th>Categoria / Responsável</th><th>Previsto</th><th>Ação</th></tr></thead><tbody>'+lines+'</tbody></table></div>':'<div class="empty-state"><b>Nenhuma provisão pendente neste filtro.</b>Cadastre o primeiro compromisso ou altere o filtro.</div>';
  return '<div class="stack provision-module">'+cards+info+
    '<section class="panel"><div class="provision-toolbar"><div><h2>Compromissos em aberto</h2><p>Pesquise e combine os filtros abaixo.</p></div></div>'+selector+listing+'<p class="table-count" id="provision-count">'+shown.length+' vencimento(s) exibido(s).</p></section></div>';
}
let provisionRequest=null;
async function loadProvisions({silent=false}={}){
  if(provisionRequest)return provisionRequest;
  provisionRequest=(async()=>{
    let changed=false;
    try{
      const answer=await api("/api/provisions");
      const latest=Array.isArray(answer.items)?answer.items:[];
      changed=provisionError!==null || !provisionItems ||
        JSON.stringify(provisionItems)!==JSON.stringify(latest);
      provisionItems=latest;
      provisionError=null;
    }catch(err){
      provisionError=err.message;
      if(page==="provisions" && !silent)render();
      throw err;
    }
    if(page==="provisions" && (!silent || changed)){
      const scroller=$("#workspace .main-area");
      const oldPosition=silent&&scroller?scroller.scrollTop:null;
      render();
      if(oldPosition!==null&&scroller)scroller.scrollTop=oldPosition;
    }
  })();
  try{return await provisionRequest}
  finally{provisionRequest=null}
}
async function openProvisionDialog(){
  await loadFinanceCatalogs(true);
  const d=$("#provision-dialog"),f=$("#provision-form");
  f.reset();
  hydrateProvisionCatalogs();
  if(!f.elements.category.options.length || f.elements.category.options.length===1 ||
     !f.elements.responsible.options.length || f.elements.responsible.options.length===1){
    throw Error("Cadastre ao menos uma categoria e um responsável em Configurações.");
  }
  f.elements.start_due_date.value=provisionToday();
  f.elements.recurrence.value="unlimited";f.elements.frequency.value="monthly";
  f.elements.value_mode.value="fixed";provisionOptions();
  d.showModal();f.elements.description.focus();
}
function provisionOptions(){
  const f=$("#provision-form"),mode=f.elements.recurrence.value;
  $("#provision-frequency-wrap").hidden=mode==="once";
  $("#provision-installments-wrap").hidden=!["until_date","installments"].includes(mode);
  $("#pv-count-label").textContent=mode==="until_date"?"Quantidade de vencimentos *":"Quantidade de parcelas *";
  f.elements.installment_count.required=["until_date","installments"].includes(mode);
}
let provisionPaymentMatches=[];
let provisionMatchesRequest=0;
async function loadPaymentMatches(){
  const f=$("#provision-payment-form"),wrap=$("#provision-match-options");
  if(!f||!wrap||!$("#provision-payment-dialog").open)return;
  const request=++provisionMatchesRequest;
  provisionPaymentMatches=[];
  wrap.innerHTML='<p class="panel-copy">Buscando lançamentos correspondentes…</p>';
  const id=Number(f.elements.occurrence_id.value),amount=Number(f.elements.amount.value);
  if(!id||!f.elements.payment_date.value||!Number.isFinite(amount)||amount<=0){
    wrap.innerHTML="Informe data e valor para buscar correspondências.";return;
  }
  try{
    const result=await api("/api/provisions/"+id+"/matches?payment_date="+
      encodeURIComponent(f.elements.payment_date.value)+"&amount="+encodeURIComponent(amount));
    if(request!==provisionMatchesRequest||!$("#provision-payment-dialog").open)return;
    provisionPaymentMatches=result.items||[];
    const suggestions=provisionPaymentMatches.map(x=>
      '<label class="provision-match-item"><input type="radio" name="match_source" value="'+esc(x.kind)+':'+Number(x.id)+'">'+
      '<span><b>'+(x.kind==="bank"?"Extrato bancário":"Registro existente")+' · '+esc(x.description)+'</b>'+
      '<small>'+dateBR(x.date)+' · '+money(x.amount)+' · '+
      (x.kind==="bank"?esc(x.account_label||"Conta #"+Number(x.account_id)):"Registro #"+Number(x.id))+
      ' · '+esc(x.reasons.join(", "))+'</small></span></label>'
    ).join("");
    wrap.innerHTML='<p class="provision-match-title">Como deseja quitar?</p>'+
      '<label class="provision-match-item"><input type="radio" name="match_source" value="new">'+
      '<span><b>Criar novo Registro</b><small>Somente quando não houver pagamento já registrado.</small></span></label>'+
      (suggestions||'<p class="panel-copy">Nenhum lançamento correspondente encontrado. Confira o histórico antes de criar um novo Registro.</p>')+
      suggestions;
    provisionPaymentMode();
  }catch(err){
    if(request!==provisionMatchesRequest)return;
    wrap.innerHTML='<p class="panel-copy">Busca de correspondências indisponível: '+esc(err.message)+
      '. Se já conferiu o histórico, selecione explicitamente a opção abaixo.</p>'+
      '<label class="provision-match-item"><input type="radio" name="match_source" value="new">'+
      '<span><b>Criar novo Registro mesmo sem sugestões</b></span></label>';
    provisionPaymentMode();
  }
}
function provisionPaymentMode(){
  const f=$("#provision-payment-form");
  const choice=f.querySelector('input[name="match_source"]:checked')?.value||"";
  const button=f.querySelector('button[type="submit"]');
  if(button)button.textContent=choice===""?"Escolher origem":choice==="new"?"Confirmar pagamento":"Vincular e quitar";
  const detail=$("#provision-payment-mode-detail");
  if(detail)detail.textContent=!choice?"Selecione como registrar o pagamento antes de confirmar.":choice==="new"?
    "Esta opção cria um novo Registro. Certifique-se de que o pagamento não esteja no histórico.":
    "Será aproveitado o pagamento escolhido, sem duplicar a despesa. Data e valor efetivos serão os do lançamento de origem.";
}
async function openPaymentDialog(id){
  const item=(provisionItems||[]).find(x=>Number(x.id)===Number(id));
  if(!item)return showToast("Provisão não encontrada. Atualize a lista.",true);
  const f=$("#provision-payment-form");f.reset();f.elements.occurrence_id.value=id;
  f.elements.payment_date.value=provisionToday();
  f.elements.amount.value=Number(item.planned_value).toFixed(2);
  $("#provision-payment-detail").textContent=(item.rule?.description||"Conta")+" · vencimento "+dateBR(item.due_date);
  $("#provision-payment-dialog").showModal();
  await loadPaymentMatches();
}
function findOpenProvision(id){
  const item=(provisionItems||[]).find(entry=>Number(entry.id)===Number(id));
  if(!item)throw Error("Vencimento não localizado. Recarregue a lista.");
  return item;
}
function provisionEffective(item,field){
  const rule=item.rule||{};
  return item[field+"_override"]||rule[field]||"";
}
async function openEditProvisionDialog(id){
  const item=findOpenProvision(id);
  await loadFinanceCatalogs(true);
  const dialog=$("#provision-edit-dialog"),form=$("#provision-edit-form");
  form.reset();
  hydrateProvisionCatalogs("#provision-edit-form");
  form.elements.occurrence_id.value=item.id;
  form.elements.description.value=provisionEffective(item,"description");
  form.elements.category.value=provisionEffective(item,"category");
  form.elements.responsible.value=provisionEffective(item,"responsible");
  form.elements.due_date.value=item.due_date;
  form.elements.planned_value.value=Number(item.planned_value).toFixed(2);
  form.elements.value_mode.value=provisionEffective(item,"value_mode");
  const once=item.rule?.recurrence==="once";
  for(const input of form.querySelectorAll('input[name="scope"]')){
    input.closest("label").hidden=once&&input.value==="future";
  }
  $("#provision-edit-detail").textContent="Vencimento "+dateBR(item.due_date)+" · "+provisionEffective(item,"description");
  dialog.showModal();
  form.elements.description.focus();
}
function openCancelProvisionDialog(id){
  const item=findOpenProvision(id),dialog=$("#provision-cancel-dialog"),form=$("#provision-cancel-form");
  form.reset();
  form.elements.occurrence_id.value=item.id;
  const once=item.rule?.recurrence==="once";
  for(const input of form.querySelectorAll('input[name="scope"]')){
    input.closest("label").hidden=once&&input.value==="future";
  }
  $("#provision-cancel-detail").textContent=provisionEffective(item,"description")+" · vencimento "+dateBR(item.due_date);
  dialog.showModal();
}
document.addEventListener("DOMContentLoaded",()=>{
  document.addEventListener("click",async e=>{
    const action=e.target.closest("[data-action]")?.dataset.action;
    if(action==="new-provision")openProvisionDialog().catch(err=>showToast(err.message,true));
    if(action==="pay-provision")openPaymentDialog(e.target.closest("[data-id]").dataset.id).catch(err=>showToast(err.message,true));
    if(action==="clear-provision-filters"){
      provisionView="all";for(const key of Object.keys(provisionFilters))provisionFilters[key]="";render();
    }
    if(action==="edit-provision")openEditProvisionDialog(e.target.closest("[data-id]").dataset.id).catch(err=>showToast(err.message,true));
    if(action==="cancel-provision")openCancelProvisionDialog(e.target.closest("[data-id]").dataset.id);
  });
  $("#provision-dialog").addEventListener("click",e=>{if(e.target.closest("[data-dismiss-provision]"))$("#provision-dialog").close()});
  $("#provision-payment-dialog").addEventListener("click",e=>{
    if(e.target.closest("[data-dismiss-payment]")){
      provisionMatchesRequest++;$("#provision-payment-dialog").close();
    }
  });
  $("#provision-payment-form").addEventListener("change",e=>{
    if(e.target.name==="match_source")provisionPaymentMode();
    if(e.target.name==="payment_date"||e.target.name==="amount")loadPaymentMatches();
  });
  $("#provision-edit-dialog").addEventListener("click",e=>{if(e.target.closest("[data-dismiss-edit]"))$("#provision-edit-dialog").close()});
  $("#provision-cancel-dialog").addEventListener("click",e=>{if(e.target.closest("[data-dismiss-cancel]"))$("#provision-cancel-dialog").close()});
  $("#provision-form").elements.recurrence.addEventListener("change",provisionOptions);
  $("#page-content").addEventListener("change",e=>{
    if(e.target.id==="provision-filter"){provisionView=e.target.value;render();}
    const filters={"provision-category-filter":"category","provision-responsible-filter":"responsible",
      "provision-from-filter":"from","provision-to-filter":"to"};
    if(filters[e.target.id]){provisionFilters[filters[e.target.id]]=e.target.value;render();}
  });
  $("#page-content").addEventListener("input",e=>{
    if(e.target.id!=="provision-search-filter")return;
    provisionFilters.search=e.target.value;const query=provisionNorm(e.target.value);
    let count=0;
    document.querySelectorAll(".provision-table tbody tr").forEach(tr=>{
      const show=!query||tr.dataset.provisionSearch.includes(query);
      tr.hidden=!show;if(show)count++;
    });
    const node=$("#provision-count");if(node)node.textContent=count+" vencimento(s) exibido(s).";
  });
  $("#provision-form").addEventListener("submit",async e=>{
    e.preventDefault();const form=e.currentTarget,btn=form.querySelector('button[type="submit"]');
    const values=Object.fromEntries(new FormData(form).entries());
    delete values.installment_count;
    if(["until_date","installments"].includes(form.elements.recurrence.value)){
      values.installment_count=Number(form.elements.installment_count.value);
    }
    values.planned_value=Number(values.planned_value);
    btn.disabled=true;
    try{
      await api("/api/provisions",{method:"POST",body:JSON.stringify(values)});
      $("#provision-dialog").close();await loadProvisions();showToast("Provisão cadastrada com sucesso.");
    }catch(err){showToast(err.message,true)}
    finally{btn.disabled=false}
  });
  $("#provision-edit-form").addEventListener("submit",async e=>{
    e.preventDefault();
    const form=e.currentTarget,button=form.querySelector('button[type="submit"]');
    const id=Number(form.elements.occurrence_id.value);
    const values=Object.fromEntries(new FormData(form).entries());
    delete values.occurrence_id;
    values.planned_value=Number(values.planned_value);
    button.disabled=true;
    try{
      const result=await api("/api/provisions/"+id,{
        method:"PATCH",body:JSON.stringify(values)
      });
      $("#provision-edit-dialog").close();
      await refresh();await loadProvisions();
      showToast(result.updated+" vencimento(s) atualizado(s).");
    }catch(err){showToast(err.message,true)}
    finally{button.disabled=false}
  });
  $("#provision-cancel-form").addEventListener("submit",async e=>{
    e.preventDefault();
    const form=e.currentTarget,button=form.querySelector('button[type="submit"]');
    if(!form.elements.confirm_cancel.checked)return;
    button.disabled=true;
    try{
      const result=await api("/api/provisions/"+Number(form.elements.occurrence_id.value)+"/cancel",{
        method:"POST",body:JSON.stringify({scope:form.elements.scope.value})
      });
      $("#provision-cancel-dialog").close();
      await refresh();await loadProvisions();
      showToast(result.cancelled+" vencimento(s) excluído(s) das pendências.");
    }catch(err){showToast(err.message,true)}
    finally{button.disabled=false}
  });
  $("#provision-payment-form").addEventListener("submit",async e=>{
    e.preventDefault();const form=e.currentTarget,btn=form.querySelector('button[type="submit"]');
    if(!form.elements.full_settlement.checked){showToast("Confirme a quitação integral do vencimento.",true);return;}
    const choice=form.querySelector('input[name="match_source"]:checked')?.value||"";
    if(!choice){showToast("Escolha criar um novo Registro ou vincular um lançamento existente.",true);return;}
    const isLink=choice!=="new";
    if(isLink&&!provisionPaymentMatches.some(x=>x.kind+":"+x.id===choice)){
      showToast("Sugestão desatualizada. Atualize a busca.",true);return;
    }
    if(!confirm(isLink?
      "Vincular lançamento existente e quitar esta previsão sem criar despesa duplicada?":
      "Confirmar quitação integral? Será criado automaticamente um novo Registro financeiro."))return;
    btn.disabled=true;
    try{
       const id=Number(form.elements.occurrence_id.value);
       if(isLink){
         const [kind,source_id]=choice.split(":");
         await api("/api/provisions/"+id+"/match",{
           method:"POST",body:JSON.stringify({kind,source_id:Number(source_id)})
         });
       }else{
         await api("/api/provisions/"+id+"/pay",{
           method:"POST",body:JSON.stringify({payment_date:form.elements.payment_date.value,amount:Number(form.elements.amount.value)})
         });
       }
      $("#provision-payment-dialog").close();
      await refresh();await loadProvisions();
      showToast(isLink?"Lançamento vinculado e previsão quitada sem duplicidade.":"Pagamento registrado e enviado para Registros.");
    }catch(err){showToast(err.message,true)}
    finally{btn.disabled=false}
  });
});
