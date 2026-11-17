/* AXORA · Operações manuais: transferências, investimentos e tipos de conta.
   Senhas, permissões e execução financeira seguem exclusivamente no servidor. */
"use strict";
const AxoraBankAdvanced=(()=>{
  let accountTypes=null,typeLoading=null,transfers=null,transferLoading=null;
  const principal=()=>!!me&&(!me.family_enabled||me.family_role==="principal");
  function types(){return accountTypes||[]}
  function typeLabel(code){
    return types().find(t=>t.code===code)?.label||{
      corrente:"Conta corrente",poupanca:"Poupança",pagamento:"Pagamento",outro:"Outro"
    }[code]||String(code||"Conta");
  }
  function loadTypes(force=false){
    if(!principal())return Promise.resolve([]);
    if(typeLoading)return typeLoading;
    if(!force&&accountTypes)return Promise.resolve(accountTypes);
    typeLoading=(async()=>{
      try{
        const result=await api("/api/banking/account-types");
        const next=result.items||[];
        const changed=!accountTypes||JSON.stringify(accountTypes)!==JSON.stringify(next);
        accountTypes=next;
        // Evita redesenhar todo o módulo quando a lista não mudou.
        if(changed&&(page==="settings"||page==="bank-accounts"))render();
        return accountTypes;
      }finally{typeLoading=null}
    })();
    return typeLoading;
  }
  function typePanel(){
    if(!principal())return "";
    if(!accountTypes)return panel("Tipos de contas","Defina as modalidades bancárias disponíveis.",
      '<p class="panel-copy">Carregando tipos cadastrados…</p>');
    const rows=accountTypes.map(t=>
      '<div class="bank-type-row"><div><b>'+esc(t.label)+'</b>'+
      '<small>'+(t.active?"Disponível para novas contas":"Inativo para novos cadastros")+'</small></div>'+
      '<button class="btn ghost small" type="button" data-action="bank-type-edit" data-id="'+Number(t.id)+'">Editar</button></div>'
    ).join("");
    return panel("Tipos de contas",
      "Crie e renomeie modalidades sem alterar o histórico das contas existentes.",
      '<div class="bank-type-toolbar"><span>'+accountTypes.length+' tipos cadastrados</span>'+
      '<button class="btn primary small" type="button" data-action="bank-type-new">Novo tipo</button></div>'+
      '<div class="bank-type-list">'+rows+'</div>');
  }
  function fillTypes(select,selected){
    select.replaceChildren(new Option("Selecione o tipo de conta",""));
    for(const type of types()){
      if(!type.active && type.code!==selected)continue;
      select.add(new Option(type.label+(type.active?"":" (inativo)"),type.code));
    }
    if(selected && !types().some(type=>type.code===selected)){
      select.add(new Option(typeLabel(selected)+" (histórico)",selected));
    }
    if(selected)select.value=selected;
  }
  function openType(id=null){
    const item=id===null?null:types().find(t=>Number(t.id)===Number(id));
    if(id!==null&&!item)throw Error("Tipo de conta não encontrado.");
    const f=$("#bank-type-form");f.reset();
    f.elements.type_id.value=item?.id||"";
    f.elements.label.value=item?.label||"";
    f.elements.active.checked=item?.active!==false;
    $("#bank-type-active-wrap").hidden=!item;
    $("#bank-type-title").textContent=item?"Editar tipo de conta":"Novo tipo de conta";
    $("#bank-type-dialog").showModal();
  }
  function availableAccounts(){
    return bankingData?.accounts?.filter(a=>
      !(bankingData.mode!=="manual" && (a.pluggy_account_id||a.pluggy_item_id)))||[];
  }
  function openInvestment(id){
    if(!principal())return;
    const a=(bankingData?.accounts||[]).find(x=>Number(x.id)===Number(id));
    if(!a)throw Error("Conta não localizada.");
    const f=$("#bank-investment-form");f.reset();
    f.elements.account_id.value=a.id;
    f.elements.investment_balance.value=a.investment_balance==null?"":Number(a.investment_balance).toFixed(2);
    $("#bank-investment-detail").textContent=a.bank_name+" · "+a.nickname;
    $("#bank-investment-dialog").showModal();
  }
  function openTransfer(sourceId=null){
    if(!principal())return;
    const accounts=availableAccounts();
    if(accounts.length<2)throw Error("Cadastre ao menos duas contas manuais para transferir.");
    const f=$("#bank-transfer-form");f.reset();delete f.dataset.requestId;
    const holders=new Map((bankingData.holders||[]).map(h=>[Number(h.id),h.name]));
    const options=accounts.map(a=>({id:a.id,label:(holders.get(Number(a.holder_id))||"Membro")+
      " · "+a.bank_name+" · "+a.nickname}));
    bankFillSelect(f.elements.from_account_id,options,"Conta de origem");
    bankFillSelect(f.elements.to_account_id,options,"Conta de destino");
    if(sourceId)f.elements.from_account_id.value=String(sourceId);
    const destination=options.find(x=>String(x.id)!==f.elements.from_account_id.value);
    if(destination)f.elements.to_account_id.value=String(destination.id);
    $("#bank-transfer-dialog").showModal();
  }
  function historyPanel(){
    if(!principal())return "";
    if(!transfers)return '<p class="panel-copy">Consulte o histórico de transferências internas. '+
      '<button type="button" class="btn ghost small" data-action="bank-transfer-history">Ver histórico</button></p>';
    const accounts=new Map((bankingData?.accounts||[]).map(a=>[Number(a.id),
      a.bank_name+" · "+a.nickname]));
    const rows=transfers.map(t=>'<div class="bank-transfer-row"><div><b>'+
      esc(accounts.get(Number(t.from_account_id))||"Conta anterior")+" → "+
      esc(accounts.get(Number(t.to_account_id))||"Conta anterior")+
      '</b><small>'+esc(String(t.created_at||"").slice(0,10).split("-").reverse().join("/"))+
      (t.note?' · '+esc(t.note):"")+'</small></div><strong>'+money(t.amount)+'</strong></div>').join("");
    return '<div class="bank-transfer-history"><div class="bank-transfer-history-head"><h3>Transferências internas</h3>'+
      '<button class="btn ghost small" type="button" data-action="bank-transfer-history">Atualizar</button></div>'+
      (rows||'<p class="panel-copy">Nenhuma transferência registrada.</p>')+'</div>';
  }
  async function loadHistory(){
    if(!principal())return;
    const r=await api("/api/banking/transfers");
    transfers=r.items||[];
    if(page==="bank-accounts")render();
  }
  function reset(){accountTypes=null;transfers=null;typeLoading=null;transferLoading=null}
  async function afterBankWrite(){
    // loadBanking já atualiza a tela se os dados mudarem; um segundo render()
    // causava fechamento das carteiras e salto da rolagem.
    await loadBanking(true);
  }
  document.addEventListener("DOMContentLoaded",()=>{
    document.addEventListener("click",async e=>{
      const target=e.target.closest("[data-action]");if(!target)return;
      const action=target.dataset.action,id=Number(target.dataset.id);
      try{
        if(action==="bank-type-new")openType();
        else if(action==="bank-type-edit")openType(id);
        else if(action==="bank-open-investments")openInvestment(id);
        else if(action==="bank-transfer-open")openTransfer(id||null);
        else if(action==="bank-transfer-history")await loadHistory();
      }catch(err){showToast(err.message,true)}
    });
    document.querySelectorAll("[data-bank-advanced-dismiss]").forEach(btn=>
      btn.addEventListener("click",()=>btn.closest("dialog").close()));
    $("#bank-type-form").addEventListener("submit",async e=>{
      e.preventDefault();const f=e.currentTarget,btn=f.querySelector('button[type=submit]');btn.disabled=true;
      try{
        const id=f.elements.type_id.value;
        await api("/api/banking/account-types"+(id?"/"+Number(id):""),{
          method:id?"PATCH":"POST",
          body:JSON.stringify(id?{label:f.elements.label.value.trim(),active:f.elements.active.checked}:
            {label:f.elements.label.value.trim()})
        });
        f.closest("dialog").close();await loadTypes(true);showToast("Tipo de conta salvo.");
      }catch(err){showToast(err.message,true)}finally{btn.disabled=false}
    });
    $("#bank-investment-form").addEventListener("submit",async e=>{
      e.preventDefault();const f=e.currentTarget,btn=f.querySelector('button[type=submit]');btn.disabled=true;
      try{
        const raw=f.elements.investment_balance.value.trim();
        await api("/api/banking/accounts/"+Number(f.elements.account_id.value)+"/investments",{
          method:"PATCH",body:JSON.stringify({investment_balance:raw===""?null:raw})
        });
        f.closest("dialog").close();await afterBankWrite();showToast("Saldo investido atualizado.");
      }catch(err){showToast(err.message,true)}finally{btn.disabled=false}
    });
    $("#bank-transfer-form").addEventListener("submit",async e=>{
      e.preventDefault();const f=e.currentTarget,btn=f.querySelector('button[type=submit]');btn.disabled=true;
      try{
        const source=Number(f.elements.from_account_id.value),
              target=Number(f.elements.to_account_id.value);
        if(!source||!target||source===target)throw Error("Selecione duas contas diferentes.");
        const amount=Number(f.elements.amount.value);
        if(!Number.isFinite(amount)||amount<=0)throw Error("Informe um valor positivo.");
        const origin=(bankingData?.accounts||[]).find(a=>Number(a.id)===source);
        if(origin?.manual_balance==null)throw Error("Informe primeiro o saldo disponível na origem.");
        if(Number(origin.manual_balance)<amount)throw Error("Saldo disponível insuficiente.");
        if(!f.dataset.requestId)f.dataset.requestId=crypto.randomUUID();
        const response=await api("/api/banking/transfers",{method:"POST",
          body:JSON.stringify({from_account_id:source,to_account_id:target,
            amount:f.elements.amount.value,note:f.elements.note.value,
            request_id:f.dataset.requestId})});
        f.closest("dialog").close();transfers=null;
        await afterBankWrite();showToast(response.transfer?.already_applied?
          "Transferência já havia sido registrada.":"Transferência interna concluída.");
      }catch(err){showToast(err.message,true)}finally{btn.disabled=false}
    });
  });
  return {loadTypes,fillTypes,typeLabel,typePanel,openTransfer,openInvestment,historyPanel,reset};
})();
window.AxoraBankAdvanced=AxoraBankAdvanced;
