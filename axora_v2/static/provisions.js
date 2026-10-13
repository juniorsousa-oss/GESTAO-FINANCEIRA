/* AXORA: Provisões (MVP de validação).
   Somente pendentes nesta tela. Pagamento completo vira Registro via RPC atômica.
   Sem reset da base, sem débito direto de contas e sem efeitos sobre a V1. */
"use strict";
let provisionItems=null;
let provisionError=null;
let provisionView="all";
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
  const shown=items.filter(x=>{
    if(provisionView==="overdue")return x.due_date<todayISO;
    if(provisionView==="month")return provisionMonth(x.due_date)===month;
    if(provisionView==="soon")return x.due_date>=todayISO&&x.due_date<=limit;
    return true;
  });
  const cards='<div class="metric-grid">'+[
     ["A vencer no mês",provisionSum(thisMonth),thisMonth.length+" ocorrência(s)"],
     ["Vencidas",provisionSum(overdue),overdue.length+" ocorrência(s) pendente(s)"],
     ["Próximos 30 dias",provisionSum(soon),soon.length+" ocorrência(s)"]
   ].map(([label,total,note])=>'<div class="metric-card"><div class="metric-label">'+label+'</div><div class="metric-value">'+money(total)+'</div><div class="metric-meta">'+note+'</div></div>').join("")+'</div>';
  const info='<div class="notice">Esta fase registra vencimentos individuais e <b>pagamentos completos</b>. Ao confirmar, a conta sai de Provisões e gera uma despesa vinculada na aba Registros. Saldos bancários, estornos e pagamentos parciais serão tratados nas etapas seguintes.</div>';
  const selector='<label class="provision-filter-label">Visualizar <select id="provision-filter"><option value="all" '+(provisionView==="all"?"selected":"")+'>Todas as pendentes</option><option value="month" '+(provisionView==="month"?"selected":"")+'>Vencimentos do mês</option><option value="overdue" '+(provisionView==="overdue"?"selected":"")+'>Vencidas</option><option value="soon" '+(provisionView==="soon"?"selected":"")+'>Próximos 30 dias</option></select></label>';
  const lines=shown.map(item=>{
    const rule=item.rule||{},late=item.due_date<todayISO;
    const type=provisionRecurrence[rule.recurrence]||"Recorrência";
    const frequency=rule.recurrence==="once"?"":(" · "+(provisionFrequency[rule.frequency]||""));
    return '<tr><td data-label="Vencimento"><strong>'+dateBR(item.due_date)+'</strong>'+(late?'<span class="status-badge red">Vencida</span>':'')+'</td>'+
      '<td data-label="Descrição"><strong>'+esc(rule.description||"")+'</strong><small>'+esc(type+frequency+(rule.recurrence==="installments"?" · Parcela "+item.sequence_no:""))+'</small></td>'+
      '<td data-label="Categoria / Responsável">'+esc(rule.category||"")+'<small>'+esc(rule.responsible||"")+'</small></td>'+
      '<td data-label="Previsto"><strong>'+money(item.planned_value)+'</strong><small>'+(rule.value_mode==="fixed"?"Valor fixo":"Valor estimado")+'</small></td>'+
      '<td data-label="Ação"><button type="button" class="btn primary small" data-action="pay-provision" data-id="'+Number(item.id)+'">Registrar pagamento</button></td></tr>';
  }).join("");
  const listing=lines?'<div class="provision-scroll"><table class="provision-table"><thead><tr><th>Vencimento</th><th>Descrição</th><th>Categoria / Responsável</th><th>Previsto</th><th>Ação</th></tr></thead><tbody>'+lines+'</tbody></table></div>':'<div class="empty-state"><b>Nenhuma provisão pendente neste filtro.</b>Cadastre o primeiro compromisso ou altere o filtro.</div>';
  return '<div class="stack provision-module">'+cards+info+
    '<section class="panel"><div class="provision-toolbar"><div><h2>Compromissos em aberto</h2><p>Pagamentos confirmados passam para Registros.</p></div>'+selector+'</div>'+listing+'<p class="table-count">'+shown.length+' vencimento(s) exibido(s).</p></section></div>';
}
async function loadProvisions(){
  try{
    const answer=await api("/api/provisions");
    provisionItems=Array.isArray(answer.items)?answer.items:[];
    provisionError=null;
  }catch(err){
    provisionError=err.message;
    if(page==="provisions")render();
    throw err;
  }
  if(page==="provisions")render();
}
function openProvisionDialog(){
  const d=$("#provision-dialog");const f=$("#provision-form");
  f.reset();f.elements.start_due_date.value=provisionToday();
  f.elements.recurrence.value="unlimited";f.elements.frequency.value="monthly";
  f.elements.value_mode.value="fixed";provisionOptions();
  d.showModal();f.elements.description.focus();
}
function provisionOptions(){
  const f=$("#provision-form"),mode=f.elements.recurrence.value;
  $("#provision-frequency-wrap").hidden=mode==="once";
  $("#provision-end-wrap").hidden=mode!=="until_date";
  $("#provision-installments-wrap").hidden=mode!=="installments";
  f.elements.end_date.required=mode==="until_date";
  f.elements.installment_count.required=mode==="installments";
}
function openPaymentDialog(id){
  const item=(provisionItems||[]).find(x=>Number(x.id)===Number(id));
  if(!item)return showToast("Provisão não encontrada. Atualize a lista.",true);
  const f=$("#provision-payment-form");f.reset();f.elements.occurrence_id.value=id;
  f.elements.payment_date.value=provisionToday();
  f.elements.amount.value=Number(item.planned_value).toFixed(2);
  $("#provision-payment-detail").textContent=(item.rule?.description||"Conta")+" · vencimento "+dateBR(item.due_date);
  $("#provision-payment-dialog").showModal();
}
document.addEventListener("DOMContentLoaded",()=>{
  document.addEventListener("click",async e=>{
    const action=e.target.closest("[data-action]")?.dataset.action;
    if(action==="new-provision")openProvisionDialog();
    if(action==="pay-provision")openPaymentDialog(e.target.closest("[data-id]").dataset.id);
  });
  $("#provision-dialog").addEventListener("click",e=>{if(e.target.closest("[data-dismiss-provision]"))$("#provision-dialog").close()});
  $("#provision-payment-dialog").addEventListener("click",e=>{if(e.target.closest("[data-dismiss-payment]"))$("#provision-payment-dialog").close()});
  $("#provision-form").elements.recurrence.addEventListener("change",provisionOptions);
  $("#page-content").addEventListener("change",e=>{
    if(e.target.id==="provision-filter"){provisionView=e.target.value;render();}
  });
  $("#provision-form").addEventListener("submit",async e=>{
    e.preventDefault();const form=e.currentTarget,btn=form.querySelector('button[type="submit"]');
    const values=Object.fromEntries(new FormData(form).entries());
    delete values.end_date;delete values.installment_count;
    if(form.elements.recurrence.value==="until_date")values.end_date=form.elements.end_date.value;
    if(form.elements.recurrence.value==="installments")values.installment_count=Number(form.elements.installment_count.value);
    values.planned_value=Number(values.planned_value);
    btn.disabled=true;
    try{
      await api("/api/provisions",{method:"POST",body:JSON.stringify(values)});
      $("#provision-dialog").close();await loadProvisions();showToast("Provisão cadastrada com sucesso.");
    }catch(err){showToast(err.message,true)}
    finally{btn.disabled=false}
  });
  $("#provision-payment-form").addEventListener("submit",async e=>{
    e.preventDefault();const form=e.currentTarget,btn=form.querySelector('button[type="submit"]');
    if(!form.elements.full_settlement.checked){showToast("Confirme a quitação integral do vencimento.",true);return;}
    if(!confirm("Confirmar quitação integral? Será criado automaticamente um Registro financeiro."))return;
    btn.disabled=true;
    try{
      await api("/api/provisions/"+Number(form.elements.occurrence_id.value)+"/pay",{
        method:"POST",body:JSON.stringify({payment_date:form.elements.payment_date.value,amount:Number(form.elements.amount.value)})
      });
      $("#provision-payment-dialog").close();
      await refresh();await loadProvisions();
      showToast("Pagamento registrado e enviado para Registros.");
    }catch(err){showToast(err.message,true)}
    finally{btn.disabled=false}
  });
});
