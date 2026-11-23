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
  // Para lançamento retroativo, os pagadores são escolhidos aqui sem tocar nas contas.
  // Com desconto, a própria titularidade da conta define quem pagou.
  function paymentCents(value){
    const number=Number(value);
    if(!Number.isFinite(number)||number<=0||
       Math.abs(Math.round(number*100)-number*100)>.00001)return null;
    return Math.round(number*100);
  }
  function manualAddPayer(form,initial=false){
    const selected=new Set([...form.querySelectorAll("[data-manual-payer]")].map(el=>Number(el.value)));
    const candidates=people().filter(p=>!selected.has(Number(p.id)));
    if(!candidates.length){
      if(!initial)showToast("Todos os membros já foram incluídos como pagadores.",true);
      return;
    }
    const defaultMember=candidates.find(p=>Number(p.id)===current())||candidates[0];
    const row=document.createElement("div");
    row.className="family-wallet-source family-manual-payer";
    const defaultAmount=initial&&paymentCents(form.elements.value.value)!==null
      ? Number(form.elements.value.value).toFixed(2):"";
    row.innerHTML='<label>Quem pagou?<select data-manual-payer aria-label="Pagador">'+
      people().map(p=>'<option value="'+Number(p.id)+'">'+esc(p.display_name)+'</option>').join("")+
      '</select></label><label>Valor pago (R$)<input type="number" data-manual-amount '+
      'inputmode="decimal" min="0.01" step="0.01" placeholder="0,00" '+
      'aria-label="Valor pago" value="'+defaultAmount+'"></label>'+
      '<button type="button" data-manual-remove aria-label="Retirar pagador">×</button>';
    form.querySelector("#family-manual-payer-list").appendChild(row);
    row.querySelector("[data-manual-payer]").value=String(defaultMember.id);
    manualTotals(form);
  }
  function manualTotals(form){
    const rows=[...form.querySelectorAll(".family-manual-payer")];
    const total=rows.reduce((sum,row)=>
      sum+(paymentCents(row.querySelector("[data-manual-amount]").value)||0),0);
    const expected=paymentCents(form.elements.value.value);
    const ids=rows.map(row=>Number(row.querySelector("[data-manual-payer]").value));
    const valid=rows.length>0 && expected!==null && total===expected &&
      ids.every(id=>people().some(p=>Number(p.id)===id))&&new Set(ids).size===ids.length&&
      rows.every(row=>paymentCents(row.querySelector("[data-manual-amount]").value)!==null);
    const output=form.querySelector("#family-manual-total");
    output.dataset.invalid=String(!valid);
    output.textContent="Pagamentos: "+money(total/100)+" de "+money((expected||0)/100)+
      (valid?"":" · confira os valores");
  }
  function manualPayments(form){
    const used=new Set(),out=[];
    for(const row of form.querySelectorAll(".family-manual-payer")){
      const profile_id=Number(row.querySelector("[data-manual-payer]").value);
      const cents=paymentCents(row.querySelector("[data-manual-amount]").value);
      if(!people().some(p=>Number(p.id)===profile_id)||used.has(profile_id)||
         cents===null)throw Error("Informe pagador e valor positivo, sem duplicar pessoas.");
      used.add(profile_id);
      out.push({profile_id,amount:cents/100});
    }
    if(!out.length||out.reduce((sum,p)=>sum+Math.round(p.amount*100),0)!==
       paymentCents(form.elements.value.value))
      throw Error("Os pagamentos precisam somar exatamente o valor do lançamento.");
    return out;
  }
  function walletPayerOptions(){
    const owners=new Set(walletAvailableAccounts().map(a=>a.profile_id));
    return people().filter(p=>owners.has(Number(p.id))).map(p=>
      '<option value="'+Number(p.id)+'">'+esc(p.display_name)+'</option>').join("");
  }
  function walletAccountOptions(profileId){
    return walletAvailableAccounts().filter(a=>a.profile_id===Number(profileId))
      .map(a=>'<option value="'+a.id+'">'+esc(a.label)+' — '+esc(money(a.balance))+
        '</option>').join("");
  }
  function walletChoosePayer(form,row){
    const payer=Number(row.querySelector("[data-wallet-payer]").value);
    const select=row.querySelector("[data-wallet-account]");
    select.innerHTML='<option value="">Selecione uma conta</option>'+
      (payer?walletAccountOptions(payer):"");
    select.disabled=!payer||!walletAvailableAccounts().some(a=>a.profile_id===payer);
    row.querySelector("[data-wallet-amount]").value="";
    walletTotals(form);
  }
  function walletChooseAccount(form,row){
    const select=row.querySelector("[data-wallet-account]");
    const account=walletAvailableAccounts().find(a=>a.id===Number(select.value));
    const payer=Number(row.querySelector("[data-wallet-payer]").value);
    const amount=row.querySelector("[data-wallet-amount]");
    const rows=[...form.querySelectorAll("#family-wallet-source-list .family-wallet-source")];
    // Primeira conta selecionada recebe o valor total como sugestão. A partir
    // da segunda, a distribuição fica explicitamente sob controle do usuário.
    if(account&&account.profile_id===payer&&rows.length===1&&
       !amount.value.trim()&&paymentCents(form.elements.value.value)!==null)
      amount.value=Number(form.elements.value.value).toFixed(2);
    walletTotals(form);
  }
  function walletAddSource(form){
    if(!walletAvailableAccounts().length){
      showToast("Nenhuma conta manual com saldo disponível foi encontrada.",true);
      return;
    }
    const row=document.createElement("div");
    row.className="family-wallet-source";
    row.innerHTML='<label>Responsável<select data-wallet-payer aria-label="Responsável pelo pagamento">'+
      '<option value="">Selecione um responsável</option>'+
      walletPayerOptions()+'</select></label>'+
      '<label>Conta de origem<select data-wallet-account aria-label="Conta de origem" disabled>'+
      '<option value="">Escolha primeiro o responsável</option></select></label>'+
      '<label>Valor (R$)<input type="number" data-wallet-amount min="0.01" step="0.01" '+
      'placeholder="0,00" inputmode="decimal" aria-label="Valor retirado da conta"></label>'+
      '<button type="button" data-wallet-remove aria-label="Retirar esta conta">×</button>'+
      '<small class="family-wallet-balance">Escolha o responsável e depois uma das contas vinculadas a ele.</small>';
    form.querySelector("#family-wallet-source-list").appendChild(row);
    walletTotals(form);
  }
  function walletTotals(form){
    const output=form.querySelector("#family-wallet-total");
    const accounts=new Map(walletAvailableAccounts().map(a=>[a.id,a]));
    const rows=[...form.querySelectorAll("#family-wallet-source-list .family-wallet-source")];
    const selected=rows.map(row=>Number(row.querySelector("[data-wallet-account]").value));
    let total=0,valid=rows.length>0;
    for(const row of rows){
      const input=row.querySelector("[data-wallet-amount]");
      const cents=paymentCents(input.value);
      const account=accounts.get(Number(row.querySelector("[data-wallet-account]").value));
      const payer=Number(row.querySelector("[data-wallet-payer]").value);
      total+=cents||0;
      if(!account||!payer||account.profile_id!==payer||cents===null||
         cents>Math.round(account.balance*100))valid=false;
      row.querySelector(".family-wallet-balance").textContent=account&&payer===account.profile_id?
        "Saldo disponível: "+money(account.balance):
        (payer?"Selecione uma conta deste responsável.":"Selecione o responsável antes da conta.");
    }
    const expected=paymentCents(form.elements.value.value);
    valid=valid&&expected!==null&&total===expected&&
      new Set(selected).size===selected.length;
    output.dataset.invalid=String(!valid);
    output.textContent="Contas: "+money(total/100)+" de "+money((expected||0)/100)+
      (valid?"":" · confira os valores");
  }
  // Entradas possuem um único recebedor; conta de destino deve ser dele.
  // É possível dividir a mesma entrada entre contas distintas desse perfil.
  function incomeAccounts(form){
    const profileId=Number(form.elements.income_profile_id.value);
    return walletAvailableAccounts().filter(a=>a.profile_id===profileId);
  }
  function incomeAddSource(form){
    const accounts=incomeAccounts(form);
    if(!accounts.length){
      showToast("Nenhuma conta manual do recebedor está disponível para crédito.",true);
      return;
    }
    const row=document.createElement("div");
    row.className="family-wallet-source";
    row.innerHTML='<label>Conta de destino<select data-income-wallet-account aria-label="Conta para receber a entrada">'+
      '<option value="">Selecione uma conta</option>'+
      accounts.map(a=>'<option value="'+a.id+'">'+esc(a.label)+' — '+esc(money(a.balance))+
        '</option>').join("")+'</select></label>'+
      '<label>Valor recebido (R$)<input data-income-wallet-amount type="number" '+
      'inputmode="decimal" min="0.01" step="0.01" placeholder="0,00" '+
      'aria-label="Valor a creditar na conta"></label>'+
      '<button type="button" data-income-wallet-remove aria-label="Remover conta de destino">×</button>'+
      '<small class="family-wallet-balance">Selecione a conta para receber a entrada.</small>';
    form.querySelector("#family-income-wallet-source-list").appendChild(row);
    incomeTotals(form);
  }
  function incomeChooseAccount(form,row){
    const account=incomeAccounts(form).find(a=>a.id===Number(row.querySelector("[data-income-wallet-account]").value));
    const amount=row.querySelector("[data-income-wallet-amount]");
    if(account && form.querySelectorAll("#family-income-wallet-source-list .family-wallet-source").length===1 &&
       !amount.value.trim() && paymentCents(form.elements.value.value)!==null){
      amount.value=Number(form.elements.value.value).toFixed(2);
    }
    incomeTotals(form);
  }
  function incomeTotals(form){
    const accounts=new Map(incomeAccounts(form).map(a=>[a.id,a]));
    const rows=[...form.querySelectorAll("#family-income-wallet-source-list .family-wallet-source")];
    let total=0,valid=rows.length>0;
    const ids=[];
    for(const row of rows){
      const id=Number(row.querySelector("[data-income-wallet-account]").value);
      const account=accounts.get(id);
      const cents=paymentCents(row.querySelector("[data-income-wallet-amount]").value);
      ids.push(id);total+=cents||0;
      if(!account||cents===null)valid=false;
      row.querySelector(".family-wallet-balance").textContent=account?
        "Saldo atual: "+money(account.balance)+" · Após crédito: "+money(account.balance+(cents||0)/100):
        "Selecione uma conta deste recebedor.";
    }
    const expected=paymentCents(form.elements.value.value);
    valid=valid && expected!==null && total===expected && new Set(ids).size===ids.length;
    const output=form.querySelector("#family-income-wallet-total");
    output.dataset.invalid=String(!valid);
    output.textContent="Créditos: "+money(total/100)+" de "+money((expected||0)/100)+
      (valid?"":" · confira os valores");
  }
  function incomeWalletSources(form){
    if(form.elements.classification.value!=="ENTRADA" ||
       form.querySelector('[name="income_balance_mode"]:checked')?.value!=="wallet")return null;
    if(!own())throw Error("Somente o principal pode atualizar saldos.");
    const profile_id=Number(form.elements.income_profile_id.value);
    const accounts=new Map(incomeAccounts(form).map(a=>[a.id,a]));
    const used=new Set(),sources=[];
    let total=0;
    for(const row of form.querySelectorAll("#family-income-wallet-source-list .family-wallet-source")){
      const account_id=Number(row.querySelector("[data-income-wallet-account]").value);
      const account=accounts.get(account_id);
      const cents=paymentCents(row.querySelector("[data-income-wallet-amount]").value);
      if(!account||account.profile_id!==profile_id||cents===null||used.has(account_id))
        throw Error("Selecione contas distintas do recebedor e valores positivos.");
      used.add(account_id);total+=cents;
      sources.push({profile_id,account_id,amount:cents/100});
    }
    if(!sources.length||total!==paymentCents(form.elements.value.value))
      throw Error("Os créditos precisam somar exatamente o valor da entrada.");
    return sources;
  }
  function walletUpdateMode(form){
    const expense=form.elements.classification.value==="SAÍDA";
    const income=form.querySelector("#family-income-recipient-wrap");
    const split=form.querySelector("#family-cost-fieldset");
    if(income)income.hidden=expense;
    if(split)split.hidden=!expense;
    form.querySelector("#family-entry-heading").textContent=form.dataset.occurrenceId?
      "Pagar provisão com rateio":expense?"Novo lançamento com rateio":"Nova entrada";
    form.querySelector('[type="submit"]').textContent=form.dataset.occurrenceId?
      "Confirmar pagamento":expense?"Salvar rateio":"Salvar entrada";
    form.querySelector("[data-family-wallet]").hidden=!expense;
    form.querySelector("#family-income-wallet-fieldset").hidden=expense;
    const incomeChoice=form.querySelector('[name="income_balance_mode"][value="wallet"]');
    const incomeAvailable=own()&&incomeAccounts(form).length>0;
    incomeChoice.disabled=!incomeAvailable;
    incomeChoice.closest("label").hidden=!own();
    if(!incomeAvailable&&incomeChoice.checked)
      form.querySelector('[name="income_balance_mode"][value="none"]').checked=true;
    const incomeWallet=!expense&&incomeAvailable&&incomeChoice.checked;
    form.querySelector("#family-income-wallet-details").hidden=!incomeWallet;
    if(incomeWallet&&!form.querySelector("#family-income-wallet-source-list .family-wallet-source"))
      incomeAddSource(form);
    if(incomeWallet)incomeTotals(form);
    const available=own()&&walletAvailableAccounts().length>0;
    const choice=form.querySelector('[name="balance_mode"][value="wallet"]');
    choice.disabled=!available;
    choice.closest("label").hidden=!own();
    if(!available&&choice.checked)
      form.querySelector('[name="balance_mode"][value="none"]').checked=true;
    const wallet=expense&&available&&choice.checked;
    form.querySelector("#family-wallet-details").hidden=!wallet;
    form.querySelector("#family-manual-details").hidden=!expense||wallet;
    if(wallet&&!form.querySelector("#family-wallet-source-list .family-wallet-source"))walletAddSource(form);
    if(wallet)walletTotals(form);
    else if(expense)manualTotals(form);
  }
  function walletPaymentSources(form){
    if(form.elements.classification.value!=="SAÍDA"||
       form.querySelector('[name="balance_mode"]:checked')?.value!=="wallet")return null;
    if(!own())throw Error("Somente o usuário principal pode movimentar o saldo.");
    const accounts=new Map(walletAvailableAccounts().map(a=>[a.id,a]));
    const used=new Set(),result=[];
    let total=0;
    for(const row of form.querySelectorAll("#family-wallet-source-list .family-wallet-source")){
      const account_id=Number(row.querySelector("[data-wallet-account]").value);
      const account=accounts.get(account_id);
      const payer=Number(row.querySelector("[data-wallet-payer]").value);
      const cents=paymentCents(row.querySelector("[data-wallet-amount]").value);
      if(!account||!payer||account.profile_id!==payer||cents===null||used.has(account_id))
        throw Error("Selecione o responsável e uma conta vinculada, sem repetições, e informe o valor.");
      if(cents>Math.round(account.balance*100))
        throw Error("Saldo insuficiente na conta "+account.label+".");
      used.add(account_id);total+=cents;
      result.push({profile_id:account.profile_id,account_id,amount:cents/100});
    }
    if(!result.length||total!==paymentCents(form.elements.value.value))
      throw Error("As contas precisam somar exatamente o valor do pagamento.");
    return result;
  }
  function paymentAllocation(form){
    if(form.elements.classification.value!=="SAÍDA")
      return {payments:[],accountSources:null};
    const sources=walletPaymentSources(form);
    if(sources===null)return {payments:manualPayments(form),accountSources:null};
    const totals=new Map();
    for(const source of sources){
      totals.set(source.profile_id,
        (totals.get(source.profile_id)||0)+Math.round(source.amount*100));
    }
    const payments=[...totals].map(([profile_id,cents])=>({profile_id,amount:cents/100}));
    return {payments,accountSources:sources};
  }
  function togglePayers(form){
    walletUpdateMode(form);
  }
  function initExpense(form,config={}){
    form.reset();
    form.querySelector("#family-wallet-source-list").replaceChildren();
    form.querySelector("#family-income-wallet-source-list").replaceChildren();
    form.querySelector("#family-manual-payer-list").replaceChildren();
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
    form.elements.income_profile_id.innerHTML=people().map(p=>
      '<option value="'+Number(p.id)+'">'+esc(p.display_name)+'</option>').join("");
    form.elements.income_profile_id.value=String(current()||Number(people()[0]?.id||0));
    manualAddPayer(form,true);
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
      (own()?memberTools(p):"")+'</div>'+
      (!own()&&Number(p.id)!==current()?
        '<p class="family-person-private-note">Perfil autorizado para visualização. Os dados financeiros desta pessoa permanecem privados.</p>':
        personMetrics(metrics))+'</article>';
  }
  function relationshipOptions(current){
    return [["conjuge","Cônjuge"],["pai","Pai"],["mae","Mãe"],["filho","Filho(a)"],["sogro","Sogro(a)"],["tio","Tio(a)"],["outro","Outro"]]
      .map(([value,label])=>'<option value="'+value+'" '+(value===current?'selected':'')+'>'+label+'</option>').join("");
  }
  function memberTools(p){
    const uid=Number(p.id);
    return '<details class="family-member-menu axora-action-menu" data-family-profile-id="'+uid+'">'+
      '<summary aria-expanded="false" aria-label="Opções do membro '+esc(p.display_name)+'" title="Ações do membro">⋮</summary>'+
      '<div class="family-member-menu-panel axora-action-menu-panel">'+
      (p.relationship==="principal"?"":'<div class="family-member-role">'+
        '<label for="family-role-'+uid+'">Vínculo familiar</label>'+
        '<select id="family-role-'+uid+'" data-family-role="'+uid+'">'+
        relationshipOptions(p.relationship)+'</select>'+
        '<button type="button" class="btn ghost small" data-family-action="save-relationship" data-id="'+uid+'">Salvar vínculo</button></div>')+
      '<button type="button" class="btn ghost small" data-family-action="set-visibility" '+
        'data-resource="perfil" data-id="'+uid+'" data-label="'+esc(p.visibility_label||"privado")+'">Visibilidade: '+
        esc(labels[p.visibility_label]||"Privado")+'</button>'+
      (p.relationship==="principal"?'':(p.linked_user_id?
       '<span class="family-access-status">Acesso individual ativo</span>':
       '<button type="button" class="btn ghost small" data-family-action="enable-login" data-id="'+uid+'">Criar acesso com senha</button>'))+
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
      '<div class="family-people">'+people().map(tableRow).join("")+'</div>'+
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
    const profile=kind==="perfil"?people().find(p=>Number(p.id)===id):null;
    const granted=new Set(profile?.visibility_viewers||[]);
    const heading=form.querySelector("#family-visibility-heading");
    heading.textContent=kind==="perfil"?"Visibilidade do membro":"Visibilidade do registro";
    form.querySelector("#family-visibility-explanation").textContent=kind==="perfil"?
      "Esta permissão mostra somente nome e vínculo familiar. Não autoriza visualizar contas, saldos, receitas, despesas ou registros financeiros.":
      "O acesso ao registro é controlado pelo servidor. Ser pagador ou beneficiário não libera outros registros.";
    form.querySelector("#family-visibility-users").innerHTML=people().filter(p=>p.linked_user_id&&p.relationship!=="principal"&&(kind!=="perfil"||Number(p.id)!==id)).map(p=>
      '<label class="family-check-row"><input type="checkbox" name="viewer" value="'+Number(p.linked_user_id)+'" '+
      (granted.has(Number(p.linked_user_id))?'checked':'')+'>'+
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
    const classification=form.elements.classification.value;
    const costs=classification==="ENTRADA"?
      [{profile_id:Number(form.elements.income_profile_id.value),percentage:100}]:
      ensureAllocation(value,Array.from(form.querySelectorAll("[data-family-beneficiario]")).map(x=>
        ({id:Number(x.dataset.familyBeneficiario),value:Number(x.value)})),"percentage");
    if(classification==="SAÍDA"&&Math.abs(costs.reduce((n,x)=>n+x.percentage,0)-100)>.001)
      throw Error("Beneficiários devem somar exatamente 100%.");
    const {payments,accountSources:expenseSources}=paymentAllocation(form);
    const accountSources=classification==="ENTRADA"?incomeWalletSources(form):expenseSources;
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
    showToast(useWallet?(classification==="ENTRADA"?
      "Entrada salva e saldos das contas atualizados.":"Pagamento salvo e saldos das contas atualizados."):
      "Registro salvo sem movimentar os saldos.");
  }
  async function undoProvisionPayment(occurrenceId){
    if(!own())throw Error("Somente o usuário principal pode desfazer pagamentos.");
    if(!Number.isSafeInteger(occurrenceId)||occurrenceId<1)
      throw Error("Identificador da provisão inválido.");
    const preview=await api("/api/family/provisions/"+occurrenceId+"/reversal-preview");
    if(preview.bank_linked)
      throw Error("Desfaça primeiro a conciliação bancária deste pagamento.");
    let reference=null;
    if(preview.needs_reference){
      const original=prompt("Provisão variável: informe o valor de referência que existia ANTES deste pagamento (R$). A reversão atualizará os próximos vencimentos:");
      if(original===null)return;
      const normalized=String(original).trim().replace(/^R\\$\\s*/,"");
      const value=Number(normalized.includes(",")?
        normalized.replace(/\\./g,"").replace(",","."):normalized);
      if(!Number.isFinite(value)||value<=0||value>999999999999.99||
         Math.abs(Math.round(value*100)-value*100)>0.00001)
        throw Error("Informe o valor anterior da provisão com até duas casas decimais.");
      reference=value;
    }
    const refund=Number(preview.restored_wallet_amount||0);
    const amount=Number(preview.paid_amount||0);
    const note=preview.linked_existing_record?
      "O registro original será preservado, apenas desvinculado da provisão.":
      "O registro criado pela quitação será retirado do histórico ativo.";
    const message="Desfazer o pagamento de "+money(amount)+" e reabrir a provisão?\\n\\n"+
      note+(refund>0?"\\nO valor de "+money(refund)+" será devolvido às contas usadas.":"\\nNenhum saldo bancário será alterado.")+
      "\\nA operação será registrada na auditoria.";
    if(!confirm(message))return;
    const body={confirm:true};
    if(reference!==null)body.reference_value=reference;
    const result=await api("/api/family/provisions/"+occurrenceId+"/undo",{
      method:"POST",body:JSON.stringify(body)});
    showToast("Pagamento desfeito. Provisão reaberta."+
      (Number(result.restored_wallet_amount)>0?" Saldos restaurados.":""));
    await refresh();
    if(typeof loadBanking==="function"&&Number(result.restored_wallet_amount)>0)
      await loadBanking(true);
    if(typeof loadProvisions==="function"&&page==="provisions")await loadProvisions();
    await load(true);
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
      if(action==="undo-provision-payment"){
        if(btn.disabled)return;
        btn.disabled=true;
        undoProvisionPayment(Number(btn.dataset.occurrenceId))
          .catch(err=>showToast(err.message,true))
          .finally(()=>{if(btn.isConnected)btn.disabled=false});
        return;
      }
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
      if(e.target.name==="income_profile_id"){
        form.querySelector("#family-income-wallet-source-list").replaceChildren();
        walletUpdateMode(form);
      }
      if(e.target.name==="classification"||e.target.name==="balance_mode"||
         e.target.name==="income_balance_mode")walletUpdateMode(form);
      if(e.target.matches("[data-income-wallet-account]"))
        incomeChooseAccount(form,e.target.closest(".family-wallet-source"));
      if(e.target.matches("[data-wallet-payer]"))
        walletChoosePayer(form,e.target.closest(".family-wallet-source"));
      if(e.target.matches("[data-wallet-account]"))
        walletChooseAccount(form,e.target.closest(".family-wallet-source"));
      if(e.target.matches("[data-manual-payer]"))manualTotals(form);
    });
    $("#family-manual-add-payer").addEventListener("click",()=>manualAddPayer($("#family-entry-form")));
    $("#family-manual-payer-list").addEventListener("click",e=>{
      const btn=e.target.closest("[data-manual-remove]");
      if(!btn)return;
      btn.closest(".family-manual-payer").remove();
      manualTotals($("#family-entry-form"));
    });
    $("#family-wallet-add-source").addEventListener("click",()=>walletAddSource($("#family-entry-form")));
    $("#family-income-add-account").addEventListener("click",()=>incomeAddSource($("#family-entry-form")));
    $("#family-income-wallet-source-list").addEventListener("click",e=>{
      const btn=e.target.closest("[data-income-wallet-remove]");
      if(!btn)return;
      btn.closest(".family-wallet-source").remove();
      incomeTotals($("#family-entry-form"));
    });
    $("#family-wallet-source-list").addEventListener("click",e=>{
      const btn=e.target.closest("[data-wallet-remove]");
      if(!btn)return;
      btn.closest(".family-wallet-source").remove();
      walletTotals($("#family-entry-form"));
    });
    $("#family-entry-form").addEventListener("input",e=>{
      const form=e.target.form;
      if(e.target.name==="value"){
        const manualRows=[...form.querySelectorAll(".family-manual-payer")];
        if(manualRows.length===1){
          const amount=manualRows[0].querySelector("[data-manual-amount]");
          if(!amount.dataset.customAmount)
            amount.value=Number(form.elements.value.value||0).toFixed(2);
        }
        manualTotals(form);
        walletTotals(form);
        incomeTotals(form);
      }
      if(e.target.matches("[data-manual-amount]")){
        e.target.dataset.customAmount="true";
        manualTotals(form);
      }
      if(e.target.matches("[data-wallet-amount]"))walletTotals(form);
      if(e.target.matches("[data-income-wallet-amount]"))incomeTotals(form);
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
        if(payload.resource_type==="perfil"){
          await load(true);
          if(page==="family")render();
        }else{
          await refresh();
          if(page==="provisions")await loadProvisions();
          if(page==="bank-accounts")await loadBanking(true);
        }
        showToast(payload.resource_type==="perfil"?"Visibilidade do membro atualizada.":"Rótulo de acesso atualizado.");
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
