/* AXORA: Provisões (MVP de validação).
   Somente pendentes nesta tela. Pagamento completo vira Registro via RPC atômica.
   Sem reset da base, sem débito direto de contas e sem efeitos sobre a V1. */
"use strict";
let provisionItems=null;
let provisionError=null;
let provisionView="all";
let provisionFiltersExpanded=false;
const provisionMobileMode=()=>typeof window!=="undefined"&&typeof window.matchMedia==="function"&&window.matchMedia("(max-width:850px)").matches;
const provisionFilters={search:"",category:"",responsible:"",visibility:"",from:"",to:""};
const provisionNorm=v=>String(v||"").normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLowerCase().trim();
const provisionSafeUrl=value=>{
  if(!value)return null;
  try{
    const parsed=new URL(String(value));
    return parsed.protocol==="https:" && parsed.hostname.includes(".") &&
      !parsed.username && !parsed.password ? parsed.href : null;
  }catch{return null;}
};
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
const provisionSum=items=>items.reduce((total,item)=>total+(item.planned_value==null?0:Number(item.planned_value)),0);
const provisionUnknown=items=>items.filter(x=>x.planned_value==null).length;
const provisionEstimate=item=>item.planned_value==null?"A definir":money(item.planned_value);
function provisionAmountOptions(form,labelId,helpId){
  const variable=form.elements.value_mode.value==="variable";
  const value=form.elements.planned_value;
  value.required=!variable;
  document.getElementById(labelId).textContent=variable?"Valor de referência (R$) · opcional":"Valor previsto (R$) *";
  document.getElementById(helpId).textContent=variable?
    "Deixe vazio até conhecer o valor. O último pagamento confirmado será referência para os próximos vencimentos.":
    "Obrigatório para contas com valor fixo.";
  if(variable)value.placeholder="Sem valor definido";
  else value.placeholder="Ex.: 150,00";
}

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
    if(me?.family_enabled&&me.family_role==="principal"&&provisionFilters.visibility&&
       (x.visibility_label||"privado")!==provisionFilters.visibility)return false;
    if(provisionFilters.from&&x.due_date<provisionFilters.from)return false;
    if(provisionFilters.to&&x.due_date>provisionFilters.to)return false;
    if(provisionFilters.search&&!provisionNorm([description,category,responsible].join(" ")).includes(provisionNorm(provisionFilters.search)))return false;
    return true;
  });
  const cards='<div class="metric-grid">'+[
     ["Total previsto",provisionSum(items),items.length+" pendente(s)"],
     ["A vencer no mês",provisionSum(thisMonth),thisMonth.length+" ocorrência(s)"],
     ["Vencidas",provisionSum(overdue),overdue.length+" ocorrência(s) pendente(s)"],
     ["Próximos 30 dias",provisionSum(soon),soon.length+" ocorrência(s)"],
     ["Reserva · 6 meses",provisionSum(reserve),reserve.length+" ocorrência(s) a vencer"]
   ].map(([label,total,note],index)=>'<div class="metric-card"><div class="metric-label">'+label+'</div><div class="metric-value">'+money(total)+'</div><div class="metric-meta">'+note+' · '+provisionUnknown([items,thisMonth,overdue,soon,reserve][index])+' sem valor definido</div></div>').join("")+'</div>';
  const info=provisionMobileMode()?
    '<details class="notice provision-info-disclosure"><summary><span>Sobre os valores previstos</span><small>Entenda como os compromissos são calculados</small></summary>'+
      '<div class="provision-info-copy">Compromissos sem prazo final continuam ativos: o sistema gera vencimentos em uma <b>janela móvel de 18 meses</b>. A última data exibida não é uma data de encerramento. O indicador <b>Reserva · 6 meses</b> considera somente os próximos seis meses, sem os vencidos. Contas de valor variável podem ficar <b>a definir</b>; elas não entram na soma até existir uma referência. Os totais são estimativas, não saldo disponível. Ao quitar, confira antes se já existe um lançamento para evitar duplicidade.</div></details>':
    '<div class="notice">Compromissos sem prazo final continuam ativos: o sistema gera vencimentos em uma <b>janela móvel de 18 meses</b>. A última data exibida não é uma data de encerramento. O indicador <b>Reserva · 6 meses</b> considera somente os próximos seis meses, sem os vencidos. Contas de valor variável podem ficar <b>a definir</b>; elas não entram na soma até existir uma referência. Os totais são estimativas, não saldo disponível. Ao quitar, confira antes se já existe um lançamento para evitar duplicidade.</div>';
  const activeFilterCount=[provisionView!=="all",...Object.values(provisionFilters).map(Boolean)].filter(Boolean).length;
  const filterOptions=(options,current,placeholder)=>'<option value="">'+placeholder+'</option>'+
    options.map(x=>'<option value="'+esc(x)+'" '+(current===x?'selected':'')+'>'+esc(x)+'</option>').join("");
  const selector='<details class="provision-filter-disclosure" '+((!provisionMobileMode()||provisionFiltersExpanded)?'open':'')+'>'+
    '<summary><span>Filtros de compromissos</span><small>'+(activeFilterCount?activeFilterCount+' ativo(s)':'Toque para filtrar')+'</small></summary>'+
    '<div class="provision-filters" aria-label="Filtros de compromissos">'+
    '<label class="provision-filter-label">Período<select id="provision-filter"><option value="all" '+(provisionView==="all"?"selected":"")+'>Todas as pendentes</option><option value="month" '+(provisionView==="month"?"selected":"")+'>Vencimentos do mês</option><option value="overdue" '+(provisionView==="overdue"?"selected":"")+'>Vencidas</option><option value="soon" '+(provisionView==="soon"?"selected":"")+'>Próximos 30 dias</option><option value="six" '+(provisionView==="six"?"selected":"")+'>Próximos 6 meses</option></select></label>'+
    '<label class="provision-filter-label">Categoria<select id="provision-category-filter">'+filterOptions(categories,provisionFilters.category,"Todas")+'</select></label>'+
    '<label class="provision-filter-label">Responsável<select id="provision-responsible-filter">'+filterOptions(responsibles,provisionFilters.responsible,"Todos")+'</select></label>'+
    (me?.family_enabled&&me.family_role==="principal"?
      '<label class="provision-filter-label">Acesso<select id="provision-visibility-filter">'+
      filterOptions(["privado","casal","familia","selecionados"],provisionFilters.visibility,"Todos os acessos")+
      '</select></label>':"")+
    '<label class="provision-filter-label">De<input type="date" id="provision-from-filter" value="'+esc(provisionFilters.from)+'"></label>'+
    '<label class="provision-filter-label">Até<input type="date" id="provision-to-filter" value="'+esc(provisionFilters.to)+'"></label>'+
    '<label class="provision-filter-label provision-filter-search">Buscar<input type="search" id="provision-search-filter" maxlength="100" value="'+esc(provisionFilters.search)+'" placeholder="Descrição, categoria ou responsável"></label>'+
    '<button class="btn ghost small provision-clear-filters" type="button" data-action="clear-provision-filters">Limpar</button></div></details>';
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
    const paymentUrl=provisionSafeUrl(rule.payment_url);
    const paymentMethod=rule.payment_method||(paymentUrl?"link":"none");
    return '<tr data-provision-search="'+esc(provisionNorm([description,category,responsible].join(" ")))+'"><td data-label="Vencimento"><strong>'+dateBR(item.due_date)+'</strong>'+(late?'<span class="status-badge red">Vencida</span>':'')+'</td>'+
      '<td data-label="Descrição"><strong>'+esc(description)+'</strong><small>'+esc(type+frequency+sequence)+'</small></td>'+
      '<td data-label="Categoria / Responsável">'+esc(category)+'<small>'+esc(responsible)+'</small></td>'+
      '<td data-label="Previsto"><strong>'+provisionEstimate(item)+'</strong><small>'+
      (mode==="fixed"?"Valor fixo":(rule.last_paid_value!=null && item.planned_value!=null &&
        Number(rule.last_paid_value)===Number(item.planned_value)?"Referência: último pagamento":"Valor variável / estimado"))+'</small></td>'+
      '<td data-label="Ação"><div class="provision-row-actions"><button type="button" class="btn primary small" data-action="pay-provision" data-id="'+id+'">Registrar pagamento</button>'+
      (paymentMethod==="link"&&paymentUrl?'<a class="btn ghost small provision-site-link" href="'+esc(paymentUrl)+'" target="_blank" rel="noopener noreferrer" title="Abrir o site de consulta ou pagamento em outra aba">Acessar site ↗</a>':'')+
      (paymentMethod==="pix"?'<button type="button" class="btn ghost small provision-pix-button" data-action="open-provision-pix" data-id="'+id+'">Gerar QR Code Pix</button>':'')+
      '<span class="provision-secondary-desktop">'+
      (me?.family_enabled && me.family_role==="principal"?
        '<button type="button" class="btn ghost small" data-family-action="set-visibility" data-resource="provisao" data-id="'+Number(item.rule_id)+'" data-label="'+esc(item.visibility_label||"privado")+'">Acesso: '+esc(item.visibility_label||"privado")+'</button>':'')+
      (me?.family_enabled && me.family_role!=="principal"?"":'<button type="button" class="btn ghost small" data-action="edit-provision" data-id="'+id+'">Editar</button>'+
        '<button type="button" class="btn ghost small provision-delete" data-action="cancel-provision" data-id="'+id+'">Excluir</button>')+
      '</span>'+
      (!(me?.family_enabled && me.family_role!=="principal")?
        '<details class="provision-mobile-actions axora-action-menu"><summary aria-expanded="false" aria-label="Mais opções de '+esc(description)+'" title="Mais opções">⋮</summary>'+
        '<div class="provision-mobile-actions-panel axora-action-menu-panel">'+
        (me?.family_enabled && me.family_role==="principal"?
          '<button type="button" class="btn ghost small" data-family-action="set-visibility" data-resource="provisao" data-id="'+Number(item.rule_id)+'" data-label="'+esc(item.visibility_label||"privado")+'">Acesso: '+esc(item.visibility_label||"privado")+'</button>':'')+
        '<button type="button" class="btn ghost small" data-action="edit-provision" data-id="'+id+'">Editar</button>'+
        '<button type="button" class="btn ghost small provision-delete" data-action="cancel-provision" data-id="'+id+'">Excluir</button>'+
        '</div></details>':'')+
      '</div></td></tr>';
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
function provisionMethodOptions(form){
  const method=form.elements.payment_method.value;
  const kind=form.elements.pix_kind.value;
  for(const el of form.querySelectorAll("[data-pay-method]")){
    const field=el.dataset.payMethod;
    el.hidden=field==="link"?method!=="link":field==="key"?(method!=="pix"||kind!=="key"):method!=="pix";
  }
  form.elements.payment_url.required=method==="link";
  form.elements.pix_value.required=method==="pix";
  form.elements.pix_receiver_name.required=method==="pix"&&kind==="key";
  form.elements.pix_receiver_city.required=method==="pix"&&kind==="key";
  form.elements.pix_value.placeholder=kind==="brcode"?
    "Cole o Pix Copia e Cola completo, iniciado por 000201":"Informe a chave Pix do recebedor";
}


async function openPixDialog(id){
  const item=findOpenProvision(Number(id));
  if(item.rule?.payment_method!=="pix")throw Error("Esta previsão não possui Pix cadastrado.");
  const dialog=$("#provision-pix-dialog");
  $("#provision-pix-result").hidden=true;
  $("#provision-pix-copy-button").disabled=true;
  $("#provision-pix-loading").hidden=false;
  $("#provision-pix-loading").textContent="Gerando QR Code com segurança...";
  $("#provision-pix-description").textContent=provisionEffective(item,"description")+
    " · vencimento "+dateBR(item.due_date);
  dialog.showModal();
  try{
    const result=await api("/api/provisions/"+Number(id)+"/pix");
    if(!dialog.open)return;
    $("#provision-pix-image").src=result.image_data;
    $("#provision-pix-copy-text").value=result.copy_paste;
    $("#provision-pix-warning").textContent=
      (result.kind==="key"?
       "QR Code de chave Pix, sem valor pré-definido. Confirme o valor e o beneficiário no banco.":
       "Código Pix Copia e Cola fornecido. Ele pode ter valor ou validade próprios; confira tudo no banco.")+
      " O QR Code não realiza nem confirma pagamentos.";
    $("#provision-pix-loading").hidden=true;
    $("#provision-pix-result").hidden=false;
    $("#provision-pix-copy-button").disabled=false;
  }catch(err){
    if(dialog.open)$("#provision-pix-loading").textContent=
      "Não foi possível gerar o QR Code: "+err.message;
  }
}


function provisionSplitMembers(){
  if(!me?.family_enabled||me?.family_role!=="principal")return [];
  return (window.AxoraFamily?.profiles?.()||[]).filter(p=>p.active);
}
function provisionSplitTotal(){
  const rows=[...document.querySelectorAll("#provision-split-participants .provision-split-participant")];
  const selected=rows.filter(row=>row.querySelector("[data-split-enabled]").checked);
  const total=selected.reduce((sum,row)=>sum+Number(row.querySelector("[data-split-percent]").value||0),0);
  const target=$("#provision-split-total");
  target.textContent="Total: "+total.toLocaleString("pt-BR",{minimumFractionDigits:2,maximumFractionDigits:2})+"% de 100%";
  target.dataset.invalid=String(!selected.length||Math.abs(total-100)>.001);
}
function provisionSplitEqual(){
  const checked=[...document.querySelectorAll("#provision-split-participants .provision-split-participant")]
    .filter(row=>row.querySelector("[data-split-enabled]").checked);
  checked.forEach((row,i)=>{
    const pct=row.querySelector("[data-split-percent]");
    pct.disabled=false;
    pct.value=((Math.floor(10000/checked.length)+(i<10000%checked.length?1:0))/100).toFixed(2);
  });
  document.querySelectorAll("#provision-split-participants .provision-split-participant").forEach(row=>{
    const on=row.querySelector("[data-split-enabled]").checked;
    const input=row.querySelector("[data-split-percent]");
    input.disabled=!on;if(!on)input.value="0";
  });
  provisionSplitTotal();
}
function provisionSplitOptions(){
  const panel=$("#provision-split-fieldset"),form=$("#provision-form");
  const responsible=form.elements.responsible.value;
  const members=provisionSplitMembers();
  const target=members.find(p=>provisionNorm(p.display_name)===provisionNorm(responsible));
  if(!target){panel.hidden=true;$("#provision-split-participants").replaceChildren();return}
  panel.hidden=false;
  $("#provision-split-participants").innerHTML=members.map(p=>{
    const active=Number(p.id)===Number(target.id);
    return '<div class="provision-split-participant"><label><input type="checkbox" data-split-enabled="'+Number(p.id)+'" '+
      (active?'checked':'')+'><span>'+esc(p.display_name)+'</span></label>'+
      '<input type="number" data-split-percent="'+Number(p.id)+'" inputmode="decimal" min="0.01" max="100" step="0.01" '+
      'value="'+(active?'100':'0')+'" '+(active?'':'disabled')+' aria-label="Percentual de '+esc(p.display_name)+'"></div>';
  }).join("");
  provisionSplitTotal();
}
function provisionReadSplit(){
  if(!me?.family_enabled||me.family_role!=="principal")return null;
  const memberIds=new Set(provisionSplitMembers().map(p=>Number(p.id)));
  const selected=[...document.querySelectorAll("#provision-split-participants .provision-split-participant")]
    .filter(row=>row.querySelector("[data-split-enabled]").checked)
    .map(row=>({profile_id:Number(row.querySelector("[data-split-enabled]").dataset.splitEnabled),
      percentage:Number(row.querySelector("[data-split-percent]").value)}));
  if(!selected.length||selected.some(p=>!memberIds.has(p.profile_id)||!Number.isFinite(p.percentage)||
      p.percentage<=0||p.percentage>100||Math.abs(Math.round(p.percentage*100)-p.percentage*100)>0.00001))
    throw Error("Selecione os participantes e informe percentuais válidos com até duas casas decimais.");
  if(Math.abs(selected.reduce((sum,p)=>sum+p.percentage,0)-100)>.001)
    throw Error("O rateio da provisão precisa totalizar exatamente 100%.");
  return selected;
}

async function openProvisionDialog(){
  await Promise.all([
    loadFinanceCatalogs(true),
    typeof loadBanking==="function" ? loadBanking(false) : Promise.resolve(null),
    me?.family_enabled&&window.AxoraFamily?AxoraFamily.load(false):Promise.resolve(null)
  ]);
  const d=$("#provision-dialog"),f=$("#provision-form");
  f.reset();
  hydrateProvisionCatalogs();
  if(!f.elements.category.options.length || f.elements.category.options.length===1 ||
     !f.elements.responsible.options.length || f.elements.responsible.options.length===1){
    throw Error("Cadastre ao menos uma categoria e um responsável em Configurações.");
  }
  f.elements.start_due_date.value=provisionToday();
  f.elements.recurrence.value="unlimited";f.elements.frequency.value="monthly";
  f.elements.value_mode.value="fixed";$("#pv-limit-recurring").checked=false;provisionOptions();
  provisionSplitOptions();
  f.elements.payment_method.value="none";provisionMethodOptions(f);
  d.showModal();f.elements.description.focus();
}
function provisionOptions(){
  const f=$("#provision-form"),mode=f.elements.recurrence.value;
  const limited=mode==="unlimited"&&$("#pv-limit-recurring").checked;
  $("#provision-frequency-wrap").hidden=mode==="once";
  $("#provision-limit-wrap").hidden=mode!=="unlimited";
  $("#provision-installments-wrap").hidden=!(limited||mode==="installments");
  $("#pv-count-label").textContent=limited?"Quantidade de vencimentos *":"Quantidade de parcelas *";
  f.elements.installment_count.required=limited||mode==="installments";
  provisionAmountOptions(f,"pv-value-label","pv-value-help");
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
  f.elements.amount.value=item.planned_value==null?"":Number(item.planned_value).toFixed(2);
  $("#provision-payment-detail").textContent=(item.description_override||item.rule?.description||"Conta")+
    " · vencimento "+dateBR(item.due_date);
  $("#provision-variable-payment-note").hidden=provisionEffective(item,"value_mode")!=="variable";
  const portal=provisionSafeUrl(item.rule?.payment_url);
  const method=item.rule?.payment_method||(portal?"link":"none");
  $("#provision-payment-portal").innerHTML=
    method==="link"&&portal?
      '<a class="btn ghost small provision-site-link" href="'+esc(portal)+
      '" target="_blank" rel="noopener noreferrer">Acessar site para consultar a conta ↗</a>':
    method==="pix"?
      '<button type="button" class="btn ghost small provision-pix-button" data-action="open-provision-pix" data-id="'+
      Number(id)+'">Gerar QR Code Pix</button>':"";
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
  await Promise.all([
    loadFinanceCatalogs(true),
    typeof loadBanking==="function" ? loadBanking(false) : Promise.resolve(null)
  ]);
  const dialog=$("#provision-edit-dialog"),form=$("#provision-edit-form");
  form.reset();
  hydrateProvisionCatalogs("#provision-edit-form");
  form.elements.occurrence_id.value=item.id;
  form.elements.description.value=provisionEffective(item,"description");
  form.elements.category.value=provisionEffective(item,"category");
  const priorResponsible=provisionEffective(item,"responsible");
  if(priorResponsible&&![...form.elements.responsible.options].some(opt=>opt.value===priorResponsible))
    form.elements.responsible.add(new Option(priorResponsible+" (histórico)",priorResponsible));
  form.elements.responsible.value=priorResponsible;
  form.elements.due_date.value=item.due_date;
  form.elements.planned_value.value=item.planned_value==null?"":Number(item.planned_value).toFixed(2);
  form.elements.value_mode.value=provisionEffective(item,"value_mode");
  provisionAmountOptions(form,"pve-value-label","pve-value-help");
  form.elements.payment_method.value=item.rule?.payment_method||
    (item.rule?.payment_url?"link":"none");
  form.elements.payment_url.value=item.rule?.payment_url||"";
  form.elements.pix_kind.value=item.rule?.pix_kind||"key";
  form.elements.pix_value.value=item.rule?.pix_value||"";
  form.elements.pix_receiver_name.value=item.rule?.pix_receiver_name||"";
  form.elements.pix_receiver_city.value=item.rule?.pix_receiver_city||"";
  provisionMethodOptions(form);
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
    if(action==="open-provision-pix")openPixDialog(e.target.closest("[data-id]").dataset.id).catch(err=>showToast(err.message,true));
    if(action==="clear-provision-filters"){
      provisionView="all";for(const key of Object.keys(provisionFilters))provisionFilters[key]="";render();
    }
    if(action==="edit-provision")openEditProvisionDialog(e.target.closest("[data-id]").dataset.id).catch(err=>showToast(err.message,true));
    if(action==="cancel-provision")openCancelProvisionDialog(e.target.closest("[data-id]").dataset.id);
  });
  $("#provision-dialog").addEventListener("click",e=>{if(e.target.closest("[data-dismiss-provision]"))$("#provision-dialog").close()});
  $("#provision-pix-dialog").addEventListener("click",e=>{
    if(e.target.closest("[data-dismiss-pix]"))$("#provision-pix-dialog").close();
  });
  $("#provision-pix-copy-button").addEventListener("click",async()=>{
    const value=$("#provision-pix-copy-text").value;
    if(!value)return;
    try{
      await navigator.clipboard.writeText(value);
      showToast("Pix Copia e Cola copiado. Confira os dados no banco antes de pagar.");
    }catch(err){
      $("#provision-pix-copy-text").select();
      showToast("Selecione e copie o código Pix manualmente.");
    }
  });
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
  $("#pv-limit-recurring").addEventListener("change",provisionOptions);
  $("#provision-form").elements.responsible.addEventListener("change",provisionSplitOptions);
  $("#provision-split-participants").addEventListener("change",e=>{
    if(e.target.matches("[data-split-enabled]"))provisionSplitEqual();
    if(e.target.matches("[data-split-percent]"))provisionSplitTotal();
  });
  $("#provision-split-participants").addEventListener("input",e=>{
    if(e.target.matches("[data-split-percent]"))provisionSplitTotal();
  });
  for(const form of [$("#provision-form"),$("#provision-edit-form")]){
    form.elements.payment_method.addEventListener("change",()=>provisionMethodOptions(form));
    form.elements.pix_kind.addEventListener("change",()=>provisionMethodOptions(form));
  }
  $("#provision-form").elements.value_mode.addEventListener("change",provisionOptions);
  $("#provision-edit-form").elements.value_mode.addEventListener("change",()=>{
    provisionAmountOptions($("#provision-edit-form"),"pve-value-label","pve-value-help");
  });
  // O evento toggle nativo é assíncrono: atualizar o estado no clique
  // garante que uma consulta/refresh imediato não reabra os filtros.
  $("#page-content").addEventListener("click",e=>{
    const summary=e.target.closest?.(".provision-filter-disclosure > summary");
    if(!summary)return;
    e.preventDefault();
    const section=summary.parentElement;
    provisionFiltersExpanded=!section.open;
    section.open=provisionFiltersExpanded;
  });
  $("#page-content").addEventListener("toggle",e=>{
    if(e.target.matches?.(".provision-filter-disclosure"))
      provisionFiltersExpanded=e.target.open;
  },true);
  $("#page-content").addEventListener("change",e=>{
    if(e.target.id==="provision-filter"){provisionView=e.target.value;render();}
    const filters={"provision-category-filter":"category","provision-responsible-filter":"responsible",
      "provision-visibility-filter":"visibility","provision-from-filter":"from","provision-to-filter":"to"};
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
    const isLimited=form.elements.recurrence.value==="unlimited"&&$("#pv-limit-recurring").checked;
    if(isLimited)values.recurrence="until_date"; // valor interno existente, compatível com dados antigos
    if(isLimited||form.elements.recurrence.value==="installments")
      values.installment_count=Number(form.elements.installment_count.value);
    values.planned_value=values.planned_value===""?null:Number(values.planned_value);
    btn.disabled=true;
    try{
      const shares=provisionReadSplit();
      if(shares)values.cost_shares=shares;
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
    values.planned_value=values.planned_value===""?null:Number(values.planned_value);
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
