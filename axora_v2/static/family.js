/* AXORA Family V2 — telas premium e integração com ACL privada do servidor.
   Nenhum rótulo é aplicado como permissão apenas no frontend. */
"use strict";
const AxoraFamily = (() => {
  let family=null,summary=null,users=[],lastError="",loading=false;
  const roleName={principal:"Principal",conjuge:"Cônjuge",filho:"Filho(a)",outro:"Outro"};
  const labels={privado:"Privado",casal:"Casal",familia:"Família",selecionados:"Selecionados"};
  const hasAccess=()=>Boolean(me?.family_enabled);
  const own=()=>me?.family_role==="principal";
  const people=()=>family?.profiles?.filter(p=>p.active)||[];
  const current=()=>Number(family?.my_profile_id||0);
  const visOpts=()=>Object.entries(labels).map(([key,title])=>
    '<option value="'+key+'">'+title+'</option>').join("");
  function labelSelect(name="label",value="privado"){
    return '<select name="'+name+'" class="family-select">'+Object.entries(labels).filter(x=>x[0]!=="selecionados").map(
      ([v,t])=>'<option value="'+v+'" '+(value===v?'selected':'')+'>'+t+'</option>').join("")+'</select>';
  }
  async function load(force=false){
    if(!hasAccess())return;
    if(loading||(!force&&family&&summary))return;
    loading=true;lastError="";
    try{
      const [f,s]=await Promise.all([api("/api/family"),api("/api/family/summary")]);
      family=f;summary=s;
      users=own()?await api("/api/users"):[];
    }catch(err){lastError=err.message}
    finally{loading=false;if(page==="family")render()}
  }
  function entryRows(type,predefined=null){
    const target=current()||Number(people()[0]?.id||0);
    return people().map(p=>{
      const id=Number(p.id),selected=id===target;
      const amount=type==="cost"?(selected?100:0):(selected?Number(predefined||0).toFixed(2):"0.00");
      const name=type==="cost"?"beneficiario":"pagador";
      return '<label class="family-allocation-row"><span>'+esc(p.display_name)+
        '<small>'+esc(roleName[p.relationship]||"Perfil")+'</small></span><input inputmode="decimal" type="number" '+
        'data-family-'+name+'="'+id+'" min="0" max="'+(type==="cost"?100:"999999999999.99")+
        '" step="0.01" value="'+amount+'" aria-label="'+(type==="cost"?"Percentual":"Pagamento")+
        ' de '+esc(p.display_name)+'"><span class="family-unit">'+(type==="cost"?"%":"R$")+'</span></label>';
    }).join("");
  }
  function togglePayers(form){
    form.querySelector("[data-family-payers]").hidden=form.elements.classification.value==="ENTRADA";
  }
  function initExpense(form,config={}){
    form.reset();
    form.dataset.occurrenceId=config.occurrence_id||"";
    form.elements.classification.value=config.occurrence_id?"SAÍDA":"SAÍDA";
    form.elements.entry_date.value=new Date().toLocaleDateString("en-CA");
    form.elements.description.value=config.description||"";
    form.elements.value.value=config.value==null?"":String(Number(config.value).toFixed(2));
    form.elements.category.value=config.category||"";
    form.elements.label.value=config.label==="casal"||config.label==="familia"?config.label:"privado";
    form.elements.classification.disabled=Boolean(config.occurrence_id);
    form.elements.description.readOnly=Boolean(config.occurrence_id);
    form.querySelector("#family-cost-list").innerHTML=entryRows("cost");
    form.querySelector("#family-payer-list").innerHTML=entryRows("payment",config.value);
    form.querySelector("#family-entry-heading").textContent=config.occurrence_id?
      "Pagar provisão com rateio":"Novo lançamento com rateio";
    form.querySelector("[data-family-provision-note]").hidden=!config.occurrence_id;
    togglePayers(form);
    $("#family-entry-dialog").showModal();
  }
  async function openEntry(config={}){
    if(!hasAccess())throw Error("Ative o ambiente familiar para utilizar o rateio.");
    if(!family)await load(true);
    if(!people().length)throw Error("Cadastre perfis antes de registrar custos.");
    initExpense($("#family-entry-form"),config);
  }
  function tableRow(p){
    const metrics=summary?.people?.find(x=>Number(x.id)===Number(p.id))||{};
    return '<article class="family-person-summary"><div class="family-person-heading"><div class="family-avatar">'+
      esc(p.display_name.slice(0,1).toUpperCase())+'</div><div><strong>'+esc(p.display_name)+
      '</strong><small>'+esc(roleName[p.relationship]||"Outro")+
      (p.linked_user_id?' · Login vinculado':' · Sem login')+'</small></div></div>'+
      '<div class="family-person-metrics"><div><span>Entradas</span><b>'+money(metrics.entradas||0)+'</b></div>'+
      '<div><span>Despesas atribuídas</span><b>'+money(metrics.despesas||0)+'</b></div>'+
      '<div><span>Efetivamente pago</span><b>'+money(metrics.pagamentos||0)+'</b></div>'+
      '<div><span>Saldo pessoal</span><b>'+money(metrics.saldo||0)+'</b></div></div></article>';
  }
  function newProfileForm(){
    return '<form id="family-profile-form" class="family-profile-form"><div class="field"><label>Nome</label>'+
      '<input name="display_name" type="text" maxlength="80" required placeholder="Nome da pessoa"></div>'+
      '<div class="field"><label>Vínculo</label><select name="relationship" required>'+
      '<option value="conjuge">Cônjuge</option><option value="filho">Filho(a)</option>'+
      '<option value="outro">Outro</option></select></div>'+
      '<div class="field full"><label>Tipo de acesso</label><select name="access_mode">'+
      '<option value="sem">Perfil financeiro sem login</option>'+
      '<option value="existente">Vincular usuário já cadastrado</option>'+
      '<option value="novo">Criar login com senha própria</option></select>'+
      '<small>Filhos podem ter os custos registrados sem acessar suas informações bancárias.</small></div>'+
      '<div class="field full" data-family-existing hidden><label>Usuário existente</label><select name="user_id">'+
      '<option value="">Selecione</option>'+users.filter(u=>u.is_active&&!u.is_admin).map(
        u=>'<option value="'+Number(u.id)+'">'+esc(u.display_name)+'</option>').join("")+'</select></div>'+
      '<div class="field full" data-family-new hidden><label>Senha exclusiva (mínimo 12 caracteres)</label>'+
      '<input type="password" name="password" minlength="12" maxlength="500" autocomplete="new-password"></div>'+
      '<button class="btn primary" type="submit">Adicionar pessoa</button></form>';
  }
  function pageHtml(){
    if(!hasAccess())return '<section class="panel"><h2>Gestão familiar indisponível</h2>'+
      '<p>Esta instância ainda não tem uma família configurada.</p></section>';
    if(lastError)return '<section class="panel"><h2>Falha ao consultar família</h2><p>'+
      esc(lastError)+'</p><button class="btn ghost" data-family-action="retry">Tentar novamente</button></section>';
    if(!family)return '<section class="panel"><h2>Gestão familiar</h2>'+
      '<p>Consultando pessoas e indicadores…</p></section>';
    const summaryNote=Number(summary?.unallocated_movements||0)>0?
      '<div class="notice warning">'+Number(summary.unallocated_movements)+
      ' registro(s) antigo(s) sem atribuição de custos; serão classificados manualmente, nunca automaticamente.</div>':"";
    return '<div class="stack family-page">'+
      '<section class="panel family-intro"><div><span class="eyebrow">AXORA FAMÍLIA</span>'+
      '<h2>Quem recebe, quanto custa e quem paga.</h2>'+
      '<p>Os totais abaixo respeitam os rótulos de privacidade de seu perfil. '+
      'Ser beneficiário ou pagador não libera acesso a contas privadas.</p></div>'+
      '<button class="btn primary" type="button" data-family-action="new-expense">Novo registro com rateio</button></section>'+
      summaryNote+
      '<div class="family-people">'+people().map(tableRow).join("")+'</div>'+
      (own()?panel("Pessoas e usuários vinculados",
        "Crie perfis sem login ou associe um usuário existente com autorização própria.",newProfileForm()):
      '<div class="notice">Você vê apenas dados próprios e compartilhados com seu perfil.</div>')+
      '</div>';
  }
  async function saveProfile(form){
    const data=Object.fromEntries(new FormData(form).entries());
    const mode=data.access_mode;
    const profile=await api("/api/family/profiles",{
      method:"POST",body:JSON.stringify({display_name:data.display_name,relationship:data.relationship})});
    if(mode!=="sem"){
      let uid=Number(data.user_id);
      if(mode==="novo"){
        if(!data.password||data.password.length<12)throw Error("Senha deve ter pelo menos 12 caracteres.");
        const created=await api("/api/users",{method:"POST",body:JSON.stringify({
          display_name:data.display_name,password:data.password})});
        uid=Number(created.id);
      }
      if(!Number.isInteger(uid)||uid<=0)throw Error("Perfil criado sem login. Selecione um usuário para vincular.");
      await api("/api/family/profiles/"+Number(profile.profile.id)+"/link",{
        method:"POST",body:JSON.stringify({user_id:uid})});
    }
    await load(true);
    showToast("Perfil familiar cadastrado.");
  }
  function openVisibility(kind,id,existing="privado"){
    if(!own())throw Error("Somente o usuário principal pode administrar rótulos.");
    const form=$("#family-visibility-form");
    form.reset();
    form.elements.resource_type.value=kind;
    form.elements.resource_id.value=id;
    form.elements.label.value=existing;
    form.querySelector("#family-visibility-users").innerHTML=people().filter(p=>p.linked_user_id&&p.relationship!=="principal").map(p=>
      '<label class="family-check-row"><input type="checkbox" name="viewer" value="'+Number(p.linked_user_id)+'">'+
      esc(p.display_name)+'</label>').join("")||'<p>Nenhum usuário secundário vinculado.</p>';
    form.querySelector("#family-visibility-users").hidden=existing!=="selecionados";
    $("#family-visibility-dialog").showModal();
  }
  function ensureAllocation(value,rows,field){
    const valid=rows.filter(x=>x.value>0).map(x=>({profile_id:x.id,[field]:x.value}));
    if(!valid.length)throw Error("Informe pelo menos um participante do rateio.");
    return valid;
  }
  async function saveTransaction(form){
    const value=Number(form.elements.value.value);
    if(!Number.isFinite(value)||value<=0)throw Error("Valor de pagamento inválido.");
    const costs=ensureAllocation(value,Array.from(form.querySelectorAll("[data-family-beneficiario]")).map(x=>
      ({id:Number(x.dataset.familyBeneficiario),value:Number(x.value)})),"percentage");
    const percent=costs.reduce((n,x)=>n+x.percentage,0);
    if(Math.abs(percent-100)>.001)throw Error("Beneficiários devem somar exatamente 100%.");
    const classification=form.elements.classification.value;
    const payments=classification==="SAÍDA"?ensureAllocation(value,
      Array.from(form.querySelectorAll("[data-family-pagador]")).map(x=>({
        id:Number(x.dataset.familyPagador),value:Number(x.value)})),"amount"):[];
    if(classification==="SAÍDA"&&Math.abs(payments.reduce((n,x)=>n+x.amount,0)-value)>.001)
      throw Error("Pagadores precisam somar o valor integral.");
    const occurrenceId=Number(form.dataset.occurrenceId||0);
    if(occurrenceId&&!confirm("Confirmar quitação? Será criado um Registro com este rateio, sem conciliação automática."))return;
    const body=occurrenceId?
      {payment_date:form.elements.entry_date.value,amount:value,label:form.elements.label.value,
        costs,payments}:
      {date:form.elements.entry_date.value,description:form.elements.description.value,
       value,classification,category:form.elements.category.value,label:form.elements.label.value,
       costs,payments};
    await api(occurrenceId?"/api/family/provisions/"+occurrenceId+"/pay":"/api/family/transactions",{
      method:"POST",body:JSON.stringify(body)});
    $("#family-entry-dialog").close();
    await refresh();
    if(occurrenceId&&typeof loadProvisions==="function")await loadProvisions();
    await load(true);
    showToast("Registro salvo com rateio por pessoa.");
  }
  document.addEventListener("DOMContentLoaded",()=>{
    document.addEventListener("click",e=>{
      // Impede o diálogo antigo de quitação quando o rateio familiar está ativo.
      const pay=e.target.closest('[data-action="pay-provision"]');
      if(pay&&hasAccess()){
        e.preventDefault();e.stopPropagation();
        const item=(provisionItems||[]).find(x=>Number(x.id)===Number(pay.dataset.id));
        if(item)openEntry({occurrence_id:item.id,description:item.description_override||item.rule?.description,
          category:item.category_override||item.rule?.category,
          value:item.planned_value,label:item.visibility_label}).catch(err=>showToast(err.message,true));
      }
    },true);
    document.addEventListener("click",e=>{
      const btn=e.target.closest("[data-family-action]");
      if(!btn)return;
      const action=btn.dataset.familyAction;
      if(action==="retry")load(true);
      if(action==="new-expense")openEntry().catch(err=>showToast(err.message,true));
      if(action==="navigate-family")go("family");
      if(action==="set-visibility")openVisibility(btn.dataset.resource,Number(btn.dataset.id),btn.dataset.label||"privado");
    });
    $("#page-content").addEventListener("change",e=>{
      if(e.target.closest("#family-profile-form")&&e.target.name==="access_mode"){
        const f=e.target.form;
        f.querySelector("[data-family-existing]").hidden=e.target.value!=="existente";
        f.querySelector("[data-family-new]").hidden=e.target.value!=="novo";
      }
    });
    $("#page-content").addEventListener("submit",e=>{
      if(e.target.id!=="family-profile-form")return;
      e.preventDefault();
      const button=e.target.querySelector('button[type="submit"]');button.disabled=true;
      saveProfile(e.target).catch(err=>showToast(err.message,true)).finally(()=>button.disabled=false);
    });
    $("#family-entry-form").addEventListener("change",e=>{
      if(e.target.name==="classification")togglePayers(e.target.form);
    });
    $("#family-entry-form").addEventListener("input",e=>{
      if(e.target.name!=="value")return;
      const form=e.target.form,ownId=current();
      const payer=form.querySelector('[data-family-pagador="'+ownId+'"]');
      const others=[...form.querySelectorAll("[data-family-pagador]")].filter(x=>x!==payer);
      if(payer&&others.every(x=>!Number(x.value)))payer.value=Number(e.target.value||0).toFixed(2);
    });
    $("#family-entry-form").addEventListener("submit",e=>{
      e.preventDefault();const btn=e.target.querySelector('button[type="submit"]');btn.disabled=true;
      saveTransaction(e.target).catch(err=>showToast(err.message,true)).finally(()=>btn.disabled=false);
    });
    $("#family-visibility-form").addEventListener("change",e=>{
      if(e.target.name==="label")e.target.form.querySelector("#family-visibility-users").hidden=e.target.value!=="selecionados";
    });
    $("#family-visibility-form").addEventListener("submit",async e=>{
      e.preventDefault();const f=e.target,btn=f.querySelector('button[type="submit"]');btn.disabled=true;
      try{
        const payload={resource_type:f.elements.resource_type.value,
          resource_id:Number(f.elements.resource_id.value),
          label:f.elements.label.value,
          viewers:[...f.querySelectorAll('input[name="viewer"]:checked')].map(x=>Number(x.value))};
        await api("/api/family/visibility",{method:"POST",body:JSON.stringify(payload)});
        $("#family-visibility-dialog").close();
        await refresh();
        if(page==="provisions")await loadProvisions();
        if(page==="bank-accounts")await loadBanking(true);
        showToast("Rótulo de acesso atualizado.");
      }catch(err){showToast(err.message,true)}
      finally{btn.disabled=false}
    });
    document.querySelectorAll("[data-family-close]").forEach(btn=>btn.addEventListener("click",()=>{
      btn.closest("dialog").close();
    }));
  });
  return {load,page:pageHtml,openEntry,openVisibility,hasAccess,own};
})();
window.AxoraFamily=AxoraFamily;
