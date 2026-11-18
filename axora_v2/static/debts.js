/* AXORA | Dívidas em aberto — cadastro isolado, renegociação atômica para Provisões. */
const AxoraDebts=(()=>{
  let items=null,members=[],loading=false,error="",pending=null;
  let view="all",searchText="";
  const owner=()=>!me?.family_enabled||me.family_role==="principal";
  const cents=x=>Math.round(Number(x||0)*100);
  const format=x=>money(Number(x||0));
  const owned=()=>members.length>0;
  const memberOptions=current=>{
    const data=owned()?members:[{id:0,name:"Próprio"}];
    return data.map(m=>'<option value="'+Number(m.id)+'" '+(m.name===current?'selected':'')+'>'+esc(m.name)+'</option>').join("");
  };
  const ownerOf=(form)=>members.find(m=>Number(m.id)===Number(form.elements.responsible.value))?.name||"Próprio";
  async function load(force=false){
    if(!owner())throw Error("Somente o principal pode consultar dívidas.");
    if(pending)return pending;
    if(items!==null&&!force)return;
    loading=true;error="";
    pending=(async()=>{
      try{
        const r=await api("/api/debts/portfolio");
        items=Array.isArray(r.items)?r.items:[];
        members=Array.isArray(r.members)?r.members:[];
      }catch(e){error=e.message;throw e}
      finally{
        loading=false;pending=null;
        if(page==="debts")render();
      }
    })();
    return pending;
  }
  const sums=rows=>{
    const overdue=rows.filter(x=>x.status!=="RENEGOCIADO");
    const agreed=rows.filter(x=>x.status==="RENEGOCIADO");
    return [
      ["Total em aberto",rows.reduce((s,x)=>s+cents(x.open_value),0)/100],
      ["Renegociado",agreed.reduce((s,x)=>s+cents(x.open_value),0)/100],
      ["Não renegociado",overdue.reduce((s,x)=>s+cents(x.open_value),0)/100],
    ];
  };
  function matches(item){
    const status=(item.status||"NÃO RENEGOCIADO");
    if(view!=="all"&&view!==status)return false;
    if(searchText&&!String([item.description,item.category,item.responsible].join(" "))
      .toLocaleLowerCase("pt-BR").includes(searchText.toLocaleLowerCase("pt-BR")))return false;
    return true;
  }
  function card(item){
    const linked=item.status==="RENEGOCIADO"&&Number(item.linked_provision_rule_id)>0;
    const remaining=Math.max(0,Number(item.total_installments||0)-Number(item.paid_installments||0));
    return '<article class="debt-card" data-debt-id="'+Number(item.id)+'" data-debt-search="'+
      esc(String([item.description,item.category,item.responsible].join(" ")).toLowerCase())+'">'+
      '<div class="debt-card-head"><div><h3>'+esc(item.description)+'</h3>'+
      '<p>'+esc(item.responsible||"Sem responsável")+' · '+esc(item.category||"Dívidas")+'</p></div>'+
      '<span class="debt-status '+(linked?'is-agreed':'is-open')+'">'+
      (linked?'Renegociada':'Não renegociada')+'</span></div>'+
      '<div class="debt-money-row"><div><small>Em aberto</small><strong>'+format(item.open_value)+'</strong></div>'+
      '<div><small>Original</small><strong>'+format(item.total_value)+'</strong></div></div>'+
      (linked?'<p class="debt-installments">'+Number(item.paid_installments||0)+' de '+
        Number(item.total_installments||0)+' parcelas pagas · '+remaining+' restantes · '+
        format(item.installment_value)+' por parcela</p>':
        '<p class="debt-installments">Sem acordo formalizado · aguardando renegociação.</p>')+
      '<div class="debt-card-actions">'+
      (linked?'<button class="btn primary small" type="button" data-debt-action="provisions" data-id="'+Number(item.id)+'">Ver provisões</button>':
        '<button class="btn primary small" type="button" data-debt-action="renegotiate" data-id="'+Number(item.id)+'">Renegociar</button>')+
      (!linked?'<details class="debt-action-menu axora-action-menu"><summary aria-label="Opções da dívida" aria-expanded="false">⋮</summary>'+
        '<div class="debt-action-panel axora-action-menu-panel">'+
        '<button type="button" class="btn ghost small" data-debt-action="edit" data-id="'+Number(item.id)+'">Editar dívida</button>'+
        '</div></details>':'')+
      '</div></article>';
  }
  function pageHtml(){
    if(!owner())return '<section class="panel">Acesso restrito ao titular principal.</section>';
    if(loading&&items===null)return '<section class="panel"><p>Carregando dívidas…</p></section>';
    if(error&&items===null)return '<section class="panel"><h2>Dívidas indisponíveis</h2><p>'+esc(error)+'</p>'+
       '<button class="btn ghost" type="button" data-debt-action="reload">Tentar novamente</button></section>';
    const rows=items||[],visible=rows.filter(matches);
    return '<div class="stack debt-page">'+
      '<div class="metric-grid">'+sums(rows).map(([l,v])=>
        '<div class="metric-card"><div class="metric-label">'+l+'</div><div class="metric-value">'+
         format(v)+'</div><div class="metric-meta">Conforme acordos e pagamentos registrados</div></div>').join("")+'</div>'+
      '<section class="panel"><div class="panel-heading"><div><h2>Minha carteira de dívidas</h2>'+
      '<p>Controle das dívidas originais e acordos. A renegociação gera parcelas em Provisões, nunca Registros pagos.</p></div></div>'+
      '<div class="debt-filters">'+
      '<label>Pesquisar<input type="search" id="debt-search" placeholder="Descrição, categoria ou responsável" value="'+esc(searchText)+'"></label>'+
      '<label>Situação<select id="debt-status-filter">'+
        [['all','Todas'],['NÃO RENEGOCIADO','Não renegociadas'],['RENEGOCIADO','Renegociadas']].
          map(([key,name])=>'<option value="'+key+'" '+(view===key?'selected':'')+'>'+name+'</option>').join("")+
      '</select></label></div>'+
      (visible.length?'<div class="debt-grid">'+visible.map(card).join("")+'</div>':
        '<div class="empty-state"><b>Nenhuma dívida encontrada.</b>Cadastre uma dívida ou altere seus filtros.</div>')+
      '<p class="table-count">'+visible.length+' dívida(s) exibida(s).</p></section></div>';
  }
  function dialog(id){
    const el=document.getElementById(id);
    if(!el)throw Error("Janela de dívida não encontrada.");
    return el;
  }
  function openEdit(id=0){
    if(!owner())throw Error("Somente o principal pode editar dívidas.");
    const debt=id?items?.find(x=>Number(x.id)===Number(id)):null;
    if(id&&!debt)throw Error("Dívida não encontrada.");
    if(debt?.linked_provision_rule_id)throw Error("Acordos vinculados a Provisões não podem ser editados aqui.");
    const form=dialog("debt-edit-form");
    form.reset();
    form.dataset.debtId=id?String(id):"";
    document.getElementById("debt-edit-heading").textContent=id?"Editar dívida":"Nova dívida";
    form.elements.description.value=debt?.description||"";
    form.elements.total_value.value=debt?.total_value||"";
    form.elements.category.value=debt?.category||"Dívidas";
    form.elements.responsible.innerHTML=memberOptions(debt?.responsible||members[0]?.name||"Próprio");
    dialog("debt-edit-dialog").showModal();
  }
  function preview(){
    const form=dialog("debt-agreement-form");
    const total=Number(form.elements.total_installments.value||0);
    const paid=Number(form.elements.paid_installments.value||0);
    const value=Number(form.elements.installment_value.value||0);
    const remaining=Number.isInteger(total)&&Number.isInteger(paid)&&paid<total?
      total-paid:0;
    const el=document.getElementById("debt-agreement-preview");
    el.textContent=remaining>0&&value>0?
      remaining+" parcela(s) serão criadas em Provisões · Saldo renegociado: "+
      format(remaining*value):"Informe quantidade, parcelas pagas e valor do acordo.";
  }
  function openAgreement(id){
    if(!owner())throw Error("Somente o principal pode renegociar dívidas.");
    const debt=items?.find(x=>Number(x.id)===Number(id));
    if(!debt||debt.status==="RENEGOCIADO"||debt.linked_provision_rule_id)
      throw Error("Dívida não encontrada ou já renegociada.");
    const form=dialog("debt-agreement-form");
    form.reset();form.dataset.debtId=String(id);
    document.getElementById("debt-agreement-subject").textContent=
      debt.description+" · Valor original: "+format(debt.total_value);
    form.elements.paid_installments.value="0";
    form.elements.first_due_date.value=today();
    form.elements.category.value=debt.category||"Dívidas";
    form.elements.responsible.innerHTML=memberOptions(debt.responsible||members[0]?.name||"Próprio");
    preview();
    dialog("debt-agreement-dialog").showModal();
  }
  function goToProvisions(id){
    const debt=items?.find(x=>Number(x.id)===Number(id));
    if(!debt?.linked_provision_rule_id)throw Error("Não há Provisão vinculada.");
    go("provisions");
    provisionView="all";
    Object.keys(provisionFilters).forEach(key=>provisionFilters[key]="");
    provisionFilters.search=debt.description;
    provisionFiltersExpanded=true;
    loadProvisions().catch(e=>showToast(e.message,true));
  }
  document.addEventListener("DOMContentLoaded",()=>{
    document.addEventListener("click",e=>{
      const close=e.target.closest?.("[data-debt-close]");
      if(close){close.closest("dialog")?.close();return;}
      const action=e.target.closest?.("[data-debt-action]");
      if(!action)return;
      try{
        const id=Number(action.dataset.id||0);
        if(action.dataset.debtAction==="new")openEdit();
        if(action.dataset.debtAction==="edit")openEdit(id);
        if(action.dataset.debtAction==="renegotiate")openAgreement(id);
        if(action.dataset.debtAction==="provisions")goToProvisions(id);
        if(action.dataset.debtAction==="reload")load(true).catch(e=>showToast(e.message,true));
      }catch(err){showToast(err.message,true)}
    });
    document.getElementById("page-content").addEventListener("change",e=>{
      if(e.target.id==="debt-status-filter"){view=e.target.value;render();}
    });
    document.getElementById("page-content").addEventListener("input",e=>{
      if(e.target.id!=="debt-search")return;
      searchText=e.target.value;
      document.querySelectorAll(".debt-card").forEach(cardEl=>{
        cardEl.hidden=!cardEl.dataset.debtSearch.includes(searchText.toLowerCase());
      });
    });
    dialog("debt-edit-form").addEventListener("submit",async e=>{
      e.preventDefault();const form=e.target,btn=form.querySelector('[type="submit"]');
      const id=Number(form.dataset.debtId||0);
      const values={
        description:form.elements.description.value,
        total_value:Number(form.elements.total_value.value),
        category:form.elements.category.value,
        responsible:ownerOf(form)
      };
      btn.disabled=true;
      try{
        await api("/api/debts/portfolio"+(id?"/"+id:""),{
          method:id?"PATCH":"POST",body:JSON.stringify(values)});
        dialog("debt-edit-dialog").close();
        await load(true);await refresh({silent:true});
        showToast(id?"Dívida atualizada.":"Dívida cadastrada, sem criar Provisões.");
      }catch(err){showToast(err.message,true)}
      finally{btn.disabled=false}
    });
    dialog("debt-agreement-form").addEventListener("input",preview);
    dialog("debt-agreement-form").addEventListener("submit",async e=>{
      e.preventDefault();const form=e.target,btn=form.querySelector('[type="submit"]');
      const id=Number(form.dataset.debtId||0);
      const profile=Number(form.elements.responsible.value||0);
      const values={
        total_installments:Number(form.elements.total_installments.value),
        paid_installments:Number(form.elements.paid_installments.value),
        installment_value:Number(form.elements.installment_value.value),
        first_due_date:form.elements.first_due_date.value,
        category:form.elements.category.value,
        responsible:ownerOf(form),
        profile_id:owned()?profile:null
      };
      if(!confirm("Criar "+(values.total_installments-values.paid_installments)+
         " parcelas em Provisões? O acordo será vinculado a esta dívida e não poderá ser duplicado."))return;
      btn.disabled=true;
      try{
        await api("/api/debts/portfolio/"+id+"/renegotiate",{
          method:"POST",body:JSON.stringify(values)});
        dialog("debt-agreement-dialog").close();
        await Promise.all([load(true),loadProvisions(),refresh({silent:true})]);
        showToast("Acordo registrado. Parcelas restantes criadas em Provisões.");
      }catch(err){showToast(err.message,true)}
      finally{btn.disabled=false}
    });
  });
  return {page:pageHtml,load,openAgreement};
})();
window.AxoraDebts=AxoraDebts;
