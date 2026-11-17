/* AXORA Family V2 — telas premium e integração com ACL privada do servidor.
   Nenhum rótulo é aplicado como permissão apenas no frontend. */
"use strict";
const AxoraFamily = (() => {
  let family=null,summary=null,lastError="",loading=false,loadRequest=null;
  const roleName={principal:"Principal",conjuge:"Cônjuge",pai:"Pai",mae:"Mãe",filho:"Filho(a)",sogro:"Sogro(a)",tio:"Tio(a)",outro:"Outro"};
  const labels={privado:"Privado",casal:"Casal",familia:"Família",selecionados:"Selecionados"};
  const hasAccess=()=>Boolean(me?.family_enabled);
  const own=()=>me?.family_role==="principal";
  const people=()=>family?.profiles?.filter(p=>p.active)||[];
  const current=()=>Number(family?.my_profile_id||0);
  function reset(){family=null;summary=null;lastError="";loading=false;}
  const visOpts=()=>Object.entries(labels).map(([key,title])=>
    '<option value="'+key+'">'+title+'</option>').join("");
  function labelSelect(name="label",value="privado"){
    return '<select name="'+name+'" class="family-select">'+Object.entries(labels).filter(x=>x[0]!=="selecionados").map(
      ([v,t])=>'<option value="'+v+'" '+(value===v?'selected':'')+'>'+t+'</option>').join("")+'</select>';
  }
  async function load(force=false){
    if(!hasAccess())return;
    // Quem abrir Provisões durante outra carga aguarda o mesmo pedido e
    // recebe a lista completa de pessoas; não cria um segundo carregamento.
    if(loadRequest)return loadRequest;
    if(!force&&family&&summary)return;
    loading=true;lastError="";
    loadRequest=(async()=>{
      try{
        const [f,s]=await Promise.all([api("/api/family"),api("/api/family/summary")]);
        family=f;summary=s;
        // Nunca consulta /api/users: a lista global não pertence ao núcleo familiar.
      }catch(err){lastError=err.message;throw err}
      finally{loading=false;if(page==="family"||page==="settings")render()}
    })();
    try{return await loadRequest}finally{loadRequest=null}
  }
  function entryRows(type,predefined=null,shares=[]){
    const target=current()||Number(people()[0]?.id||0);
    const planned=new Map((shares||[]).map(s=>[Number(s.profile_id),Number(s.percentage)]));
    return people().map(p=>{
      const id=Number(p.id),selected=id===target;
      const amount=type==="cost"?(planned.size?(planned.get(id)||0):(selected?100:0)):
        (selected?Number(predefined||0).toFixed(2):"0.00");
      const name=type==="cost"?"beneficiario":"pagador";
      return '<label class="family-allocation-row"><span>'+esc(p.display_name)+
        '<small>'+esc(roleName[p.relationship]||"Perfil")+'</small></span><input inputmode="decimal" type="number" '+
        'data-family-'+name+'="'+id+'" min="0" max="'+(type==="cost"?100:"999999999999.99")+
        '" step="0.01" value="'+amount+'" aria-label="'+(type==="cost"?"Percentual":"Pagamento")+
        ' de '+esc(p.display_name)+'"><span class="family-unit">'+(type==="cost"?"%":"R$")+'</span></label>';
    }).join("");
  }

  // Carteira do próprio workspace. Subusuários não recebem esta seleção nem
  // podem modificar saldos; permissões continuam validadas pelo servidor.
  function walletAvailableAccounts(){
    if(!own()||!bankingData||bankingData.mode!=="manual")return [];
    const holders=new Map((bankingData.holders||[]).map(h=>[Number(h.id),h]));
    return (bankingData.accounts||[]).flatMap(a=>{
      const holder=holders.get(Number(a.holder_id));
      if(!holder||!Number.isInteger(Number(holder.family_profile_id))||
         Number(holder.family_profile_id)<1||a.manual_balance==null||
         a.pluggy_account_id||a.pluggy_item_id)return [];
      return [{id:Number(a.id),profile_id:Number(holder.family_profile_id),
        label:[a.bank_name,a.nickname].filter(Boolean).join(" · "),
        balance:Number(a.manual_balance)}];
    }).filter(a=>Number.isFinite(a.balance)).sort((a,b)=>a.label.localeCompare(b.label,"pt-BR"));
  }
  function walletPayingProfiles(form){
    return people().filter(p=>{
      const input=form.querySelector('[data-family-pagador="'+Number(p.id)+'"]');
      return input&&Number(input.value)>0;
    });
  }
  function walletAccountSelect(form,row,previous=0){
    const payer=Number(row.querySelector("[data-wallet-payer]").value);
    const select=row.querySelector("[data-wallet-account]");
    const accounts=walletAvailableAccounts().filter(a=>a.profile_id===payer);
    select.innerHTML='<option value="">Selecione uma conta</option>'+
      accounts.map(a=>'<option value="'+a.id+'">'+esc(a.label)+' — '+esc(money(a.balance))+'</option>').join("");
    if(accounts.some(a=>a.id===Number(previous)))select.value=String(previous);
    walletTotals(form);
  }
  function walletAddSource(form){
    const payers=walletPayingProfiles(form);
    if(!payers.length){showToast("Informe quem pagou antes de selecionar as contas.",true);return}
    const accounts=walletAvailableAccounts();
    const row=document.createElement("div");
    row.className="family-wallet-source";
    row.innerHTML='<label>Pagador<select data-wallet-payer aria-label="Pessoa pagadora">'+
      payers.map(p=>'<option value="'+Number(p.id)+'">'+esc(p.display_name)+'</option>').join("")+'</select></label>'+
      '<label>Conta de origem<select data-wallet-account aria-label="Conta de origem"></select></label>'+
      '<label>Valor (R$)<input type="number" data-wallet-amount min="0.01" step="0.01" '+
      'placeholder="0,00" inputmode="decimal" aria-label="Valor retirado da conta"></label>'+
      '<button type="button" data-wallet-remove aria-label="Retirar esta conta">×</button>'+
      '<small class="family-wallet-balance">Selecione a conta para consultar o saldo.</small>';
    form.querySelector("#family-wallet-source-list").appendChild(row);
    // Prefere uma pessoa com pagamento informado e contas cadastradas.
    const defaultPayer=payers.find(p=>accounts.some(a=>a.profile_id===Number(p.id)))||payers[0];
    row.querySelector("[data-wallet-payer]").value=String(defaultPayer.id);
    walletAccountSelect(form,row);
  }
  function walletRefreshPayers(form){
    const payers=walletPayingProfiles(form);
    form.querySelectorAll(".family-wallet-source").forEach(row=>{
      const select=row.querySelector("[data-wallet-payer]"),old=Number(select.value);
      select.innerHTML=payers.map(p=>'<option value="'+Number(p.id)+'">'+esc(p.display_name)+'</option>').join("");
      if(payers.some(p=>Number(p.id)===old))select.value=String(old);
      walletAccountSelect(form,row,Number(row.querySelector("[data-wallet-account]").value));
    });
    walletTotals(form);
  }
  function walletTotals(form){
    const output=form.querySelector("#family-wallet-total");
    const amount=Number(form.elements.value.value)||0;
    const rows=[...form.querySelectorAll(".family-wallet-source")];
    const total=rows.reduce((n,row)=>n+(Number(row.querySelector("[data-wallet-amount]").value)||0),0);
    const perPayer=new Map();
    for(const row of rows){
      const id=Number(row.querySelector("[data-wallet-payer]").value);
      perPayer.set(id,(perPayer.get(id)||0)+(Number(row.querySelector("[data-wallet-amount]").value)||0));
      const account=walletAvailableAccounts().find(a=>a.id===Number(row.querySelector("[data-wallet-account]").value));
      row.querySelector(".family-wallet-balance").textContent=account?
        "Saldo informado: "+money(account.balance):"Selecione uma conta da carteira.";
    }
    const payers=walletPayingProfiles(form);
    const valid=payers.length>0&&rows.length>0&&Math.abs(total-amount)<.001&&
      payers.every(p=>{
        const input=form.querySelector('[data-family-pagador="'+Number(p.id)+'"]');
        return Math.abs((perPayer.get(Number(p.id))||0)-Number(input.value))<.001;
      });
    output.dataset.invalid=String(!valid);
    output.textContent="Contas: "+money(total)+" de "+money(amount)+(valid?"":" · confira o rateio");
  }
  function walletUpdateMode(form){
    const expenses=form.elements.classification.value==="SAÍDA";
    const block=form.querySelector("[data-family-wallet]");
    block.hidden=!expenses;
    const available=own()&&walletAvailableAccounts().length>0;
    const choice=form.querySelector('[name="balance_mode"][value="wallet"]');
    choice.disabled=!available;
    choice.closest("label").hidden=!own();
    if(!available&&choice.checked)form.querySelector('[name="balance_mode"][value="none"]').checked=true;
    const active=expenses&&available&&choice.checked;
    form.querySelector("#family-wallet-details").hidden=!active;
    if(active&&!form.querySelector(".family-wallet-source"))walletAddSource(form);
    if(active)walletRefreshPayers(form);
  }
  function walletPaymentSources(form){
    if(form.elements.classification.value!=="SAÍDA"||
      form.querySelector('[name="balance_mode"]:checked')?.value!=="wallet")return null;
    if(!own())throw Error("A movimentação de saldos é exclusiva do usuário principal.");
    const accounts=new Map(walletAvailableAccounts().map(a=>[a.id,a]));
    const totals=new Map(),used=new Set();
    const result=[...form.querySelectorAll(".family-wallet-source")].map(row=>{
      const profile_id=Number(row.querySelector("[data-wallet-payer]").value);
      const account_id=Number(row.querySelector("[data-wallet-account]").value);
      const raw=row.querySelector("[data-wallet-amount]").value;
      const amount=Number(raw),account=accounts.get(account_id);
      if(!account||account.profile_id!==profile_id||!raw||!Number.isFinite(amount)||
         amount<=0||Math.abs(Math.round(amount*100)-amount*100)>.00001)
        throw Error("Escolha conta, pagador e valor positivo com até dois decimais.");
      if(used.has(account_id))throw Error("Uma conta só pode aparecer uma vez no mesmo pagamento.");
      used.add(account_id);
      if(amount>account.balance+.001)throw Error("Saldo insuficiente em "+account.label+".");
      totals.set(profile_id,(totals.get(profile_id)||0)+Math.round(amount*100));
      return {profile_id,account_id,amount};
    });
    if(!result.length)throw Error("Selecione ao menos uma conta de origem.");
    const payers=walletPayingProfiles(form);
    for(const payer of payers){
      const value=Number(form.querySelector('[data-family-pagador="'+Number(payer.id)+'"]').value);
      if(totals.get(Number(payer.id))!==Math.round(value*100))
        throw Error("As contas de "+payer.display_name+" precisam somar "+money(value)+".");
    }
    const total=Math.round(Number(form.elements.value.value)*100);
    if([...totals.values()].reduce((a,b)=>a+b,0)!==total)
      throw Error("Os valores das contas devem somar o pagamento integral.");
    return result;
  }
  function togglePayers(form){
    form.querySelector("[data-family-payers]").hidden=form.elements.classification.value==="ENTRADA";
    walletUpdateMode(form);
  }
  function initExpense(form,config={}){
    form.reset();
    form.querySelector("#family-wallet-source-list").replaceChildren();
    form.dataset.walletRequestId=crypto.randomUUID();
    form.dataset.occurrenceId=config.occurrence_id||"";
    form.elements.classification.value=config.occurrence_id?"SAÍDA":"SAÍDA";
    form.elements.entry_date.value=new Date().toLocaleDateString("en-CA");
    form.elements.description.value=config.description||"";
    form.elements.value.value=config.value==null?"":String(Number(config.value).toFixed(2));
    form.elements.category.value=config.category||"";
    form.elements.label.value=config.label==="casal"||config.label==="familia"?config.label:"privado";
    form.elements.classification.disabled=Boolean(config.occurrence_id);
    form.elements.description.readOnly=Boolean(config.occurrence_id);
    form.querySelector("#family-cost-list").innerHTML=entryRows("cost",null,config.shares);
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
    if(own()&&typeof loadBanking==="function")await loadBanking(false).catch(()=>null);
    // Rateio planejado é sugerido na quitação, mas o usuário pode revisá-lo.
    // O endpoint não revela os percentuais de terceiros aos subusuários.
    if(config.rule_id&&own()){
      const planned=await api("/api/family/provisions/"+Number(config.rule_id)+"/shares");
      config={...config,shares:planned.shares||[]};
    }
    initExpense($("#family-entry-form"),config);
  }
  function personMetrics(data, pending=false){
    // Somente informações agregadas devolvidas pelo backend para esta sessão.
    // Um membro bancário sem perfil de rateio ainda não tem atribuições.
    const items=[["Entradas","entradas"],["Despesas atribuídas","despesas"],
      ["Efetivamente pago","pagamentos"],["Saldo pessoal","saldo"]];
    return '<div class="family-person-metrics">'+items.map(([label,key])=>
      '<div><span>'+label+'</span><b>'+money(data?.[key]||0)+'</b></div>').join("")+
      '</div>'+(pending?'<p class="family-bank-status">Ainda sem lançamentos de rateio atribuídos.</p>':"");
  }
  function tableRow(p){
    const metrics=summary?.people?.find(x=>Number(x.id)===Number(p.id))||{};
    return '<article class="family-person-summary"><div class="family-person-heading"><div class="family-avatar">'+
      esc(p.display_name.slice(0,1).toUpperCase())+'</div><div class="family-person-identity"><strong>'+esc(p.display_name)+
      '</strong><small>'+esc(roleName[p.relationship]||"Outro")+
      (own()?(p.linked_user_id?' · Login vinculado':' · Sem login'):'')+'</small></div>'+
      (own()&&p.relationship!=="principal"?memberTools(p):"")+'</div>'+
      personMetrics(metrics)+'</article>';
  }
  function relationshipOptions(current){
    return [["conjuge","Cônjuge"],["pai","Pai"],["mae","Mãe"],["filho","Filho(a)"],["sogro","Sogro(a)"],["tio","Tio(a)"],["outro","Outro"]]
      .map(([value,label])=>'<option value="'+value+'" '+(value===current?'selected':'')+'>'+label+'</option>').join("");
  }
  function memberTools(p){
    const uid=Number(p.id);
    return '<details class="family-member-menu" data-family-profile-id="'+uid+'">'+
      '<summary aria-label="Opções do membro '+esc(p.display_name)+'" title="Ações do membro">⋮</summary>'+
      '<div class="family-member-menu-panel"><div class="family-member-role">'+
      '<label for="family-role-'+uid+'">Vínculo familiar</label>'+
      '<select id="family-role-'+uid+'" data-family-role="'+uid+'">'+
      relationshipOptions(p.relationship)+'</select>'+
      '<button type="button" class="btn ghost small" data-family-action="save-relationship" data-id="'+uid+'">Salvar vínculo</button></div>'+
      (p.linked_user_id?
       '<span class="family-access-status">Acesso individual ativo</span>':
       '<button type="button" class="btn ghost small" data-family-action="enable-login" data-id="'+uid+'">Criar acesso com senha</button>')+
      '</div></details>';
  }
  function newProfileForm(){
    return '<form id="family-profile-form" class="family-profile-form">'+
      '<div class="field"><label for="family-new-name">Nome da pessoa</label>'+
      '<input id="family-new-name" name="display_name" type="text" maxlength="80" required placeholder="Nome do familiar"></div>'+
      '<div class="field"><label for="family-new-role">Vínculo</label><select id="family-new-role" name="relationship" required>'+
      relationshipOptions("conjuge")+'</select></div>'+
      '<div class="field full"><label for="family-new-mode">Tipo de cadastro</label>'+
      '<select id="family-new-mode" name="access_mode">'+
      '<option value="login">Subusuário com acesso próprio</option>'+
      '<option value="perfil">Apenas perfil financeiro, sem login</option></select>'+
      '<small>Uma pessoa sem login pode receber despesas atribuídas a ela, mas não entra no aplicativo.</small></div>'+
      '<div class="field full family-access-fields" data-family-credentials>'+
      '<div class="field"><label for="family-member-password">Senha exclusiva (mínimo 12 caracteres)</label>'+
      '<input id="family-member-password" name="password" type="password" minlength="12" maxlength="500" autocomplete="new-password" required></div>'+
      '<div class="field"><label for="family-member-confirm">Confirmar senha</label>'+
      '<input id="family-member-confirm" name="confirm_password" type="password" minlength="12" maxlength="500" autocomplete="new-password" required></div>'+
      '<small>O subusuário entra apenas com a própria senha e recebe somente informações autorizadas por rótulo.</small></div>'+
      '<button class="btn primary" type="submit">Cadastrar na minha família</button></form>';
  }
  function bankOnlyMembers(){
    if(!own()||typeof bankingHolderOptions!=="function")return [];
    const linkedUserIds=new Set(people().filter(p=>p.linked_user_id).map(p=>Number(p.linked_user_id)));
    const named=new Set(people().map(p=>String(p.display_name||"").trim().toLocaleLowerCase("pt-BR")));
    return bankingHolders().filter(h=>
      !(h.linked_user_id && linkedUserIds.has(Number(h.linked_user_id))) &&
      !named.has(String(h.name||"").trim().toLocaleLowerCase("pt-BR")));
  }
  function bankMemberRow(h){
    const relation=typeof holderRelations!=="undefined" ?
      (holderRelations[h.relationship]||"Familiar") : "Familiar";
    return '<article class="family-bank-only"><div class="family-person-heading">'+
      '<div class="family-avatar">'+esc((h.name||"M").trim().slice(0,1).toUpperCase())+'</div>'+
      '<div class="family-person-identity"><strong>'+esc(h.name)+'</strong><small>'+esc(relation)+
      ' · Membro financeiro</small></div></div>'+
      personMetrics(null,true)+
      '<p class="family-bank-status">Cadastro e vínculo para rateios disponíveis somente em Configurações.</p></article>';
  }
  async function activateBankMember(holderId){
    if(!own())throw Error("Somente o principal pode criar perfis de rateio.");
    const holder=bankOnlyMembers().find(h=>Number(h.id)===holderId);
    if(!holder)throw Error("Membro bancário não encontrado ou já vinculado a perfil.");
    const name=String(holder.name||"").trim();
    if(!name)throw Error("Nome do membro não informado.");
    const relationship=["conjuge","pai","mae","filho","sogro","tio"].includes(holder.relationship)?holder.relationship:"outro";
    await api("/api/family/members",{
      method:"POST",body:JSON.stringify({display_name:name,relationship,password:null})
    });
    await load(true);
    showToast("Perfil de rateio habilitado para "+name+". Nenhum acesso criado.");
  }
  function settingsPanel(){
    if(!own())return "";
    if(lastError)return '<p class="notice warning">'+esc(lastError)+'</p>';
    if(!family)return '<p class="panel-copy">Carregando cadastro familiar…</p>';
    const bankOnly=bankOnlyMembers();
    return '<div class="family-registry-settings">'+
      '<p class="panel-copy">Este é o único ponto para cadastrar familiares, com ou sem acesso próprio. Os perfis são vinculados às contas e aos rateios sem liberar dados privados automaticamente.</p>'+
      newProfileForm()+
      (bankOnly.length?'<div class="family-bank-setup-list"><h3>Vincular membros bancários existentes</h3>'+
        '<p class="panel-copy">Para evitar cadastros duplicados, habilite o perfil financeiro de quem já possui contas vinculadas.</p>'+
        bankOnly.map(h=>'<div class="family-registry-legacy"><span>'+esc(h.name)+
          ' · '+esc(holderRelations[h.relationship]||"Outro")+'</span>'+
          '<button type="button" class="btn ghost small" data-family-action="activate-bank-member" data-holder-id="'+Number(h.id)+'">Habilitar rateios</button></div>').join("")+
        '</div>':"")+
      '</div>';
  }
  function pageHtml(){
    if(!hasAccess())return '<section class="panel"><h2>Gestão familiar indisponível</h2>'+
      '<p>Esta instância ainda não tem uma família configurada.</p></section>';
    if(lastError)return '<section class="panel"><h2>Falha ao consultar família</h2><p>'+
      esc(lastError)+'</p><button class="btn ghost" data-family-action="retry">Tentar novamente</button></section>';
    if(!family)return '<section class="panel"><h2>Gestão familiar</h2>'+
      '<p>Consultando pessoas e indicadores…</p></section>';
    const summaryNote=own()&&Number(summary?.unallocated_movements||0)>0?
      '<div class="notice warning">'+Number(summary.unallocated_movements)+
      ' registro(s) antigo(s) sem atribuição de custos; serão classificados manualmente, nunca automaticamente.</div>':"";
    return '<div class="stack family-page">'+
      '<section class="panel family-intro"><div><span class="eyebrow">AXORA FAMÍLIA</span>'+
      '<h2>'+(own()?'Minha família e usuários':'Minha organização financeira')+'</h2>'+
      '<p>'+(own()?'Principal: '+esc(me.display_name)+' · Espaço independente'+
        (family.workspace_name?' · '+esc(family.workspace_name):''):
        'Entradas, gastos e pagamentos por pessoa.')+'</p></div>'+
      '<button class="btn primary" type="button" data-family-action="new-expense">Novo registro com rateio</button></section>'+
      summaryNote+
      '<div class="family-people">'+(own()?people():people().filter(p=>Number(p.id)===current())).map(tableRow).join("")+'</div>'+
      (own()&&bankOnlyMembers().length?
        panel("Demais membros cadastrados","Pessoas associadas a contas bancárias, ainda sem perfil de rateio.",
          '<div class="family-bank-grid">'+bankOnlyMembers().map(bankMemberRow).join("")+'</div>'):"")+
      '</div>';
  }
  async function saveProfile(form){
    if(!own())throw Error("Somente o principal pode cadastrar pessoas.");
    const values=Object.fromEntries(new FormData(form).entries());
    const mode=values.access_mode;
    if(!["login","perfil"].includes(mode))throw Error("Selecione o tipo de cadastro.");
    if(mode==="login" && (values.password.length<12||values.password!==values.confirm_password))
      throw Error("As senhas precisam coincidir e ter pelo menos 12 caracteres.");
    const result=await api("/api/family/members",{method:"POST",body:JSON.stringify({
      display_name:values.display_name,relationship:values.relationship,
      password:mode==="login"?values.password:null
    })});
    form.reset();
    // Após cadastrar perfil sem login, o formulário volta à opção com senha.
    const credentials=form.querySelector("[data-family-credentials]");
    if(credentials)credentials.hidden=false;
    for(const input of form.querySelectorAll("[data-family-credentials] input"))input.required=true;
    await loadBanking(true);
    await load(true);
    showToast(result.access==="login"?"Subusuário cadastrado com acesso próprio.":"Perfil financeiro cadastrado.");
  }
  async function saveRelationship(profileId,btn){
    if(!own())throw Error("Ação exclusiva da conta principal.");
    const section=btn.closest(".family-member-menu");
    const relationship=section?.querySelector("[data-family-role]")?.value;
    if(!relationship)throw Error("Selecione o vínculo.");
    await api("/api/family/profiles/"+profileId+"/relationship",
      {method:"POST",body:JSON.stringify({relationship})});
    await load(true);
    showToast("Vínculo familiar atualizado.");
  }
  function showEnableLogin(profileId){
    if(!own())throw Error("Ação exclusiva da conta principal.");
    const target=people().find(p=>Number(p.id)===profileId);
    if(!target||target.relationship==="principal"||target.linked_user_id)throw Error("Perfil indisponível.");
    const form=$("#family-access-form");
    form.reset();
    form.dataset.profileId=String(profileId);
    $("#family-access-person").textContent=target.display_name;
    $("#family-access-dialog").showModal();
  }
  async function saveLoginAccess(form){
    if(!own())throw Error("Ação exclusiva da conta principal.");
    const profileId=Number(form.dataset.profileId);
    const password=form.elements.password.value;
    if(password.length<12||password!==form.elements.confirm_password.value)
      throw Error("As senhas precisam coincidir e ter pelo menos 12 caracteres.");
    await api("/api/family/profiles/"+profileId+"/enable-login",
      {method:"POST",body:JSON.stringify({password})});
    form.reset();
    $("#family-access-dialog").close();
    await load(true);
    showToast("Acesso individual ativado.");
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
    const accountSources=walletPaymentSources(form);
    const useWallet=accountSources!==null;
    const occurrenceId=Number(form.dataset.occurrenceId||0);
    if(occurrenceId&&!confirm(useWallet?
      "Confirmar quitação e descontar "+money(value)+" das contas escolhidas?":
      "Confirmar quitação sem alterar os saldos? Será criado um Registro de pagamento."))return;
    const body=occurrenceId?
      {payment_date:form.elements.entry_date.value,amount:value,label:form.elements.label.value,
        costs,payments}:
      {date:form.elements.entry_date.value,description:form.elements.description.value,
       value,classification,category:form.elements.category.value,label:form.elements.label.value,
       costs,payments};
    if(useWallet){
      body.balance_mode="wallet";
      body.account_sources=accountSources;
      body.request_id=form.dataset.walletRequestId;
    }
    await api(occurrenceId?"/api/family/provisions/"+occurrenceId+"/pay":"/api/family/transactions",{
      method:"POST",body:JSON.stringify(body)});
    $("#family-entry-dialog").close();
    await refresh();
    if(useWallet&&typeof loadBanking==="function")await loadBanking(true);
    if(occurrenceId&&typeof loadProvisions==="function")await loadProvisions();
    await load(true);
    showToast(useWallet?"Pagamento salvo e saldos das contas atualizados.":"Registro salvo sem movimentar os saldos.");
  }
  document.addEventListener("DOMContentLoaded",()=>{
    document.addEventListener("click",e=>{
      // Impede o diálogo antigo de quitação quando o rateio familiar está ativo.
      const pay=e.target.closest('[data-action="pay-provision"]');
      if(pay&&hasAccess()){
        e.preventDefault();e.stopPropagation();
        const item=(provisionItems||[]).find(x=>Number(x.id)===Number(pay.dataset.id));
        if(item)openEntry({occurrence_id:item.id,rule_id:item.rule_id,
          description:item.description_override||item.rule?.description,
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
      if(action==="enable-login")try{showEnableLogin(Number(btn.dataset.id))}catch(err){showToast(err.message,true)}
      if(action==="save-relationship"){
        btn.disabled=true;
        saveRelationship(Number(btn.dataset.id),btn).catch(err=>showToast(err.message,true))
          .finally(()=>{btn.disabled=false});
      }
      if(action==="set-visibility")openVisibility(btn.dataset.resource,Number(btn.dataset.id),btn.dataset.label||"privado");
      if(action==="activate-bank-member"){
        btn.disabled=true;
        activateBankMember(Number(btn.dataset.holderId))
          .catch(err=>showToast(err.message,true))
          .finally(()=>{if(btn.isConnected)btn.disabled=false});
      }
    });
    $("#page-content").addEventListener("change",e=>{
      if(e.target.closest("#family-profile-form")&&e.target.name==="access_mode"){
        const f=e.target.form;
        const active=e.target.value==="login";
        f.querySelector("[data-family-credentials]").hidden=!active;
        for(const input of f.querySelectorAll("[data-family-credentials] input")){
          input.required=active;
          if(!active)input.value="";
        }
      }
    });
    $("#page-content").addEventListener("submit",e=>{
      if(e.target.id!=="family-profile-form")return;
      e.preventDefault();
      const button=e.target.querySelector('button[type="submit"]');button.disabled=true;
      saveProfile(e.target).catch(err=>showToast(err.message,true)).finally(()=>button.disabled=false);
    });
    $("#family-access-form").addEventListener("submit",e=>{
      e.preventDefault();
      const btn=e.target.querySelector('button[type="submit"]');
      btn.disabled=true;
      saveLoginAccess(e.target).catch(err=>showToast(err.message,true))
        .finally(()=>btn.disabled=false);
    });
    $("#family-entry-form").addEventListener("change",e=>{
      const form=e.target.form;
      if(e.target.name==="classification")togglePayers(form);
      if(e.target.name==="balance_mode")walletUpdateMode(form);
      if(e.target.matches("[data-wallet-payer]"))walletAccountSelect(form,e.target.closest(".family-wallet-source"));
      if(e.target.matches("[data-wallet-account]"))walletTotals(form);
    });
    $("#family-wallet-add-source").addEventListener("click",()=>walletAddSource($("#family-entry-form")));
    $("#family-wallet-source-list").addEventListener("click",e=>{
      const btn=e.target.closest("[data-wallet-remove]");
      if(!btn)return;
      btn.closest(".family-wallet-source").remove();
      walletTotals($("#family-entry-form"));
    });
    $("#family-entry-form").addEventListener("input",e=>{
      const form=e.target.form;
      if(e.target.name==="value"){
        const ownId=current();
        const payer=form.querySelector('[data-family-pagador="'+ownId+'"]');
        const others=[...form.querySelectorAll("[data-family-pagador]")].filter(x=>x!==payer);
        if(payer&&others.every(x=>!Number(x.value)))payer.value=Number(e.target.value||0).toFixed(2);
      }
      if(e.target.name==="value"||e.target.matches("[data-family-pagador]"))walletRefreshPayers(form);
      if(e.target.matches("[data-wallet-amount]"))walletTotals(form);
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
  return {load,page:pageHtml,settingsPanel,openEntry,openVisibility,hasAccess,own,reset,
    profiles:()=>own()?people():[]};
})();
window.AxoraFamily=AxoraFamily;
