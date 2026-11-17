"use strict";
// Exercita o mesmo módulo de rateio usado no navegador sem servidor financeiro.
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const assert=require("node:assert/strict");
const original=fs.readFileSync(path.join(__dirname,"../static/family.js"),"utf8");
const injection="return {__test:{paymentAllocation,paymentCents,manualPayments,walletPaymentSources,walletPayerOptions,walletAccountOptions,walletChooseAccount},load,page:pageHtml";
assert.ok(original.includes("return {load,page:pageHtml"),"Contrato de exportação não encontrado");
const source=original.replace("return {load,page:pageHtml",injection);
const members=[
  {id:1,display_name:"Principal",relationship:"principal",active:true},
  {id:2,display_name:"Cônjuge",relationship:"conjuge",active:true},
  {id:3,display_name:"Familiar",relationship:"outro",active:true},
];
const accounts=[
  {id:10,holder_id:100,bank_name:"Banco teste",nickname:"A",manual_balance:200},
  {id:11,holder_id:101,bank_name:"Banco teste",nickname:"B",manual_balance:80},
  {id:12,holder_id:100,bank_name:"Banco teste",nickname:"C",manual_balance:80},
];
const ctx=vm.createContext({
  me:{id:10,family_enabled:true,family_role:"principal"},
  bankingData:{mode:"manual",accounts,holders:[
    {id:100,family_profile_id:1},{id:101,family_profile_id:2}]},
  page:"provisions",
  document:{addEventListener(){}},
  window:{},
  api:async url=>url==="/api/family"?
    {profiles:members,my_profile_id:1}: {people:[]},
  esc:x=>String(x),
  money:x=>"R$ "+Number(x).toFixed(2),
  showToast(msg){throw Error(msg)},
  console,Math,Number,Date,Set,Map,Promise,
});
vm.runInContext(source,ctx,{filename:"family.js"});
function rowManual(id,amount){
  return {querySelector(sel){
    if(sel==="[data-manual-payer]")return {value:String(id)};
    if(sel==="[data-manual-amount]")return {value:String(amount)};
    throw Error("unexpected manual selector "+sel);
  }};
}
function rowBank(id,amount,payer=({10:1,11:2,12:1})[id]){
  const state={account:{value:String(id)},payer:{value:String(payer)},
    amount:{value:String(amount)},hint:{textContent:""}};
  return {state,querySelector(sel){
    if(sel==="[data-wallet-account]")return state.account;
    if(sel==="[data-wallet-payer]")return state.payer;
    if(sel==="[data-wallet-amount]")return state.amount;
    if(sel===".family-wallet-balance")return state.hint;
    throw Error("unexpected bank selector "+sel);
  }};
}
function form(mode,manualRows=[],bankRows=[],value=99.07,classification="SAÍDA"){
  return {
    elements:{classification:{value:classification},value:{value:String(value)}},
    querySelector(sel){
      if(sel==='[name="balance_mode"]:checked')return {value:mode};
      throw Error("unexpected selector "+sel);
    },
    querySelectorAll(sel){
      if(sel===".family-manual-payer")return manualRows;
      if(sel==="#family-wallet-source-list .family-wallet-source")return bankRows;
      throw Error("unexpected list selector "+sel);
    },
  };
}
function output(input){
  const result=vm.runInContext("AxoraFamily.__test.paymentAllocation(form)",Object.assign(ctx,{form:input}));
  return JSON.parse(JSON.stringify(result));
}
(async()=>{
  await vm.runInContext("AxoraFamily.load(true)",ctx);
  // Lançamento retroativo: a pessoa e o valor são informados nesta etapa.
  let result=output(form("none",[rowManual(1,60),rowManual(2,39.07)],[]));
  assert.deepEqual(result,{payments:[
    {profile_id:1,amount:60},{profile_id:2,amount:39.07}],accountSources:null});
  // Mesmo com linhas bancárias pré-preenchidas, modo sem saldo não debita nada.
  result=output(form("none",[rowManual(3,99.07)],[rowBank(10,99.07)]));
  assert.deepEqual(result,{payments:[{profile_id:3,amount:99.07}],accountSources:null});
  // Banco define automaticamente o pagador, sem segunda atribuição.
  result=output(form("wallet",[rowManual(3,99.07)],
    [rowBank(10,60),rowBank(11,39.07)]));
  assert.deepEqual(result,{payments:[
    {profile_id:1,amount:60},{profile_id:2,amount:39.07}],
    accountSources:[
      {profile_id:1,account_id:10,amount:60},
      {profile_id:2,account_id:11,amount:39.07}]});
  // Várias contas da mesma pessoa são agregadas, sem criar pagadores duplicados.
  result=output(form("wallet",[],
    [rowBank(10,30),rowBank(12,30),rowBank(11,39.07)]));
  assert.deepEqual(result.payments,[
    {profile_id:1,amount:60},{profile_id:2,amount:39.07}]);
  // Impede total divergente, conta repetida, saldo insuficiente e pessoa duplicada.
  assert.throws(()=>output(form("wallet",[],[rowBank(10,80)])),/somar/i);
  assert.throws(()=>output(form("wallet",[],[
    rowBank(10,60),rowBank(10,39.07)])),/repeti/i);
  assert.throws(()=>output(form("wallet",[],[
    rowBank(11,99.07)])),/insuficiente/i);
  assert.throws(()=>output(form("none",[rowManual(1,60),rowManual(1,39.07)])),/duplicar/i);
  // Responsáveis são filtrados antes de escolher conta; nunca mistura titulares.
  const payerOptions=vm.runInContext("AxoraFamily.__test.walletPayerOptions()",ctx);
  assert.ok(payerOptions.includes('value="1"'));
  assert.ok(payerOptions.includes('value="2"'));
  assert.ok(!payerOptions.includes('value="3"'),"Membro sem conta não deve aparecer");
  const owner1=vm.runInContext("AxoraFamily.__test.walletAccountOptions(1)",ctx);
  const owner2=vm.runInContext("AxoraFamily.__test.walletAccountOptions(2)",ctx);
  assert.ok(owner1.includes('value="10"')&&owner1.includes('value="12"'));
  assert.ok(!owner1.includes('value="11"'));
  assert.ok(owner2.includes('value="11"')&&!owner2.includes('value="10"'));

  // No primeiro pagante, a conta selecionada recebe o valor total sugerido.
  const initial=rowBank(10,"");
  const outputEl={dataset:{},textContent:""};
  const firstForm={
    elements:{value:{value:"99.07"},classification:{value:"SAÍDA"}},
    querySelector(sel){
      if(sel==="#family-wallet-total")return outputEl;
      throw Error("unexpected form selector "+sel);
    },
    querySelectorAll(sel){
      if(sel==="#family-wallet-source-list .family-wallet-source")return [initial];
      throw Error("unexpected list selector "+sel);
    }
  };
  Object.assign(ctx,{form:firstForm,row:initial});
  vm.runInContext("AxoraFamily.__test.walletChooseAccount(form,row)",ctx);
  assert.equal(initial.state.amount.value,"99.07","Primeiro pagador deve sugerir o valor integral");
  const manual=rowBank(10,"37.15");
  Object.assign(ctx,{form:{
    ...firstForm,querySelectorAll:()=>[manual]},row:manual});
  vm.runInContext("AxoraFamily.__test.walletChooseAccount(form,row)",ctx);
  assert.equal(manual.state.amount.value,"37.15","Não alterar valor editado manualmente");
  // Impede atribuição de uma conta de um membro ao responsável errado.
  assert.throws(()=>output(form("wallet",[],[rowBank(10,99.07,2)])),/conta vinculada/i);

  // Receita não exige pagadores e nunca debita contas.
  assert.deepEqual(output(form("wallet",[],[rowBank(10,99.07)],99.07,"ENTRADA")),
    {payments:[],accountSources:null});
  // Secundário não pode movimentar conta, mesmo simulando o radio ativo.
  ctx.me.family_role="conjuge";
  assert.throws(()=>output(form("wallet",[],[rowBank(10,99.07)])),/Somente o usuário principal/);
  console.log("AXORA: pagamento único por pagador ou conta, 10 cenários validados");
})().catch(err=>{console.error(err);process.exitCode=1});
