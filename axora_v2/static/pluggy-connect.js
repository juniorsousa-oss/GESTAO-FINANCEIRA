/* AXORA · Ligação opcional Pluggy (leitura; nunca concilia automaticamente). */
"use strict";
let axoraPluggySession=null;
let axoraPluggySdkPromise=null;

function axoraLoadPluggySdk(){
  if(typeof window.PluggyConnect==="function")return Promise.resolve();
  if(axoraPluggySdkPromise)return axoraPluggySdkPromise;
  axoraPluggySdkPromise=new Promise((resolve,reject)=>{
    const script=document.createElement("script");
    // Widget hospedado pelo próprio provedor, versão fixa. Sem credenciais longas aqui.
    script.src="https://cdn.pluggy.ai/pluggy-connect/v2.7.0/pluggy-connect.js";
    script.async=true;
    script.onload=()=>typeof window.PluggyConnect==="function"?
      resolve():reject(Error("O componente Pluggy não carregou corretamente."));
    script.onerror=()=>reject(Error("O navegador bloqueou a conexão com o componente Pluggy."));
    document.head.appendChild(script);
  }).catch(e=>{axoraPluggySdkPromise=null;throw e});
  return axoraPluggySdkPromise;
}

async function axoraPluggyStart(accountId){
  const account=(bankingData?.accounts||[]).find(a=>Number(a.id)===Number(accountId));
  if(!account)throw Error("Conta não localizada no AXORA.");
  if(!bankingData?.provider?.configured)
    throw Error("Para conectar, configure primeiro as credenciais de desenvolvedor Pluggy na Hostinger.");
  const owner=(bankingData.holders||[]).find(h=>Number(h.id)===Number(account.holder_id));
  const agreement="A conexão será vinculada à conta \""+account.nickname+"\" de "+(owner?.name||"titular")+
    ". O titular deve autorizar o compartilhamento diretamente na instituição. Continuar?";
  if(!window.confirm(agreement))return;
  await axoraLoadPluggySdk();
  const data=await api("/api/banking/pluggy/start",{method:"POST",
    body:JSON.stringify({account_id:accountId,consent_confirmed:true})});
  axoraPluggySession={intent_id:data.intent_id,account_id:accountId};
  const options={
    connectToken:data.connect_token,
    includeSandbox:data.sandbox===true,
    language:"pt",theme:"light",
    products:["ACCOUNTS","TRANSACTIONS"],
    onSuccess:async ({item})=>{
      try{
        if(!item?.id||!axoraPluggySession)return;
        const result=await api("/api/banking/pluggy/complete",{method:"POST",
          body:JSON.stringify({intent_id:axoraPluggySession.intent_id,item_id:item.id})});
        axoraPluggyShowAccounts(result);
      }catch(error){showToast(error.message,true)}
    },
    onError:()=>showToast("O provedor não concluiu a autorização. Confira a instituição e tente novamente.",true)
  };
  if(data.sandbox){
    // Não apresenta bancos reais enquanto o piloto está restrito a dados fictícios.
    options.connectorIds=[Number(data.sandbox_connector_id)];
  }else{
    options.includeSandbox=false;
  }
  new window.PluggyConnect(options).init();
}

function axoraPluggyShowAccounts(result){
  const form=document.querySelector("#bank-pluggy-account-form");
  if(!form)throw Error("Seletor de contas indisponível.");
  form.reset();
  form.elements.intent_id.value=result.intent_id;
  form.elements.item_id.value=result.item_id;
  const select=form.elements.provider_account_id;
  select.replaceChildren(new Option("Escolha a conta que corresponde ao cadastro AXORA",""));
  for(const account of result.accounts||[]){
    const label=account.label+" · "+account.owner+
      (account.last_digits?" · final "+account.last_digits:"")+
      (account.balance!=null?" · "+money(account.balance):"");
    select.add(new Option(label,account.id));
  }
  document.querySelector("#bank-pluggy-dialog").showModal();
}

async function axoraPluggyLink(form){
  const button=form.querySelector('button[type="submit"]');
  const data=Object.fromEntries(new FormData(form).entries());
  if(!form.elements.confirm_account.checked)throw Error("Confirme a identificação da conta.");
  button.disabled=true;
  try{
    const result=await api("/api/banking/pluggy/link",{method:"POST",body:JSON.stringify({
      intent_id:data.intent_id,item_id:data.item_id,
      provider_account_id:data.provider_account_id,confirm_account:true
    })});
    form.closest("dialog").close();
    axoraPluggySession=null;
    await loadBanking(true);
    showToast("Conta vinculada em modo "+(result.sandbox?"teste":"Open Finance")+". Use Sincronizar extrato para trazer movimentações.");
  }finally{button.disabled=false}
}

async function axoraPluggySync(accountId){
  if(!window.confirm("Buscar saldo e até 100 transações recentes desta conta? Tudo ficará pendente na Conciliação; nenhuma provisão será quitada automaticamente."))return;
  const data=await api("/api/banking/pluggy/sync/"+Number(accountId),{
    method:"POST",body:"{}"
  });
  await loadBanking(true);
  showToast(data.received+" transação(ões) recebidas para análise. Conciliação manual obrigatória.");
}

document.addEventListener("DOMContentLoaded",()=>{
  document.addEventListener("click",async event=>{
    const b=event.target.closest('[data-action="pluggy-start"],[data-action="pluggy-sync"]');
    if(!b||b.disabled)return;
    b.disabled=true;
    try{
      const id=Number(b.dataset.id);
      if(b.dataset.action==="pluggy-start")await axoraPluggyStart(id);
      else await axoraPluggySync(id);
    }catch(error){showToast(error.message,true)}
    finally{b.disabled=false}
  });
  document.querySelectorAll("[data-pluggy-dismiss]").forEach(b=>b.addEventListener("click",()=>{
    document.querySelector("#bank-pluggy-dialog").close();
  }));
  document.querySelector("#bank-pluggy-account-form").addEventListener("submit",async event=>{
    event.preventDefault();
    try{await axoraPluggyLink(event.currentTarget)}
    catch(error){showToast(error.message,true)}
  });
});
