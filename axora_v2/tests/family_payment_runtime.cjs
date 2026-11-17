"use strict";
// Exercita o mesmo módulo de rateio usado no navegador sem servidor financeiro.
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const assert=require("node:assert/strict");
const original=fs.readFileSync(path.join(__dirname,"../static/family.js"),"utf8");
const injection="return {__test:{paymentAllocation,paymentCents,manualPayments,walletPaymentSources},load,page:pageHtml";
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
function rowBank(id,amount){
  return {querySelector(sel){
    if(sel==="[data-wallet-account]")return {value:String(id)};
    if(sel==="[data-wallet-amount]")return {value:String(amount)};
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
  // Receita não exige pagadores e nunca debita contas.
  assert.deepEqual(output(form("wallet",[],[rowBank(10,99.07)],99.07,"ENTRADA")),
    {payments:[],accountSources:null});
  // Secundário não pode movimentar conta, mesmo simulando o radio ativo.
  ctx.me.family_role="conjuge";
  assert.throws(()=>output(form("wallet",[],[rowBank(10,99.07)])),/Somente o usuário principal/);
  console.log("AXORA: pagamento único por pagador ou conta, 10 cenários validados");
})().catch(err=>{console.error(err);process.exitCode=1});
