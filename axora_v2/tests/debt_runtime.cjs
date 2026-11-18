"use strict";
const fs=require("node:fs"),path=require("node:path"),vm=require("node:vm"),assert=require("node:assert/strict");
const source=fs.readFileSync(path.join(__dirname,"../static/debts.js"),"utf8");
const context=vm.createContext({
  document:{addEventListener(){}},window:{},me:{id:1,family_enabled:true,family_role:"principal"},
  page:"debts",render(){},money:v=>"R$ "+Number(v).toFixed(2),
  esc:v=>String(v),today:()=>"2026-11-18",go(){},loadProvisions:async()=>{},
  provisionFilters:{},provisionView:"all",provisionFiltersExpanded:false,
  api:async uri=>{
    assert.equal(uri,"/api/debts/portfolio");
    return {members:[{id:10,name:"Titular"}],items:[
      {id:1,description:"Cartão de teste",category:"Dívidas",responsible:"Titular",
        status:"NÃO RENEGOCIADO",total_value:"1481.00",open_value:"1481.00",
        total_installments:0,paid_installments:0,installment_value:"0.00"},
      {id:2,description:"Acordo de teste",category:"Dívidas",responsible:"Titular",
        status:"RENEGOCIADO",total_value:"2200.00",open_value:"650.00",
        total_installments:12,paid_installments:2,installment_value:"65.00",
        linked_provision_rule_id:100},
    ]};
  },
  console,Promise,Number,Math,Set,Date,String,Object,
});
vm.runInContext(source,context,{filename:"debts.js"});
(async()=>{
  const debts=context.window.AxoraDebts;
  assert.ok(debts&&typeof debts.page==="function");
  await debts.load(true);
  const html=debts.page();
  assert.match(html,/Cartão de teste/);
  assert.match(html,/Acordo de teste/);
  assert.match(html,/R\$ 1481\.00/);
  assert.match(html,/R\$ 650\.00/);
  assert.match(html,/10 restantes/);
  assert.match(html,/data-debt-action="renegotiate"/);
  assert.match(html,/data-debt-action="provisions"/);
  assert.match(html,/data-debt-action="edit"/);
  context.me.family_role="conjuge";
  assert.match(debts.page(),/Acesso restrito/);
  await assert.rejects(()=>debts.load(true),/Somente o principal/);
  console.log("AXORA: dívidas isoladas, acordos e resumo do portfolio verificados");
})().catch(err=>{console.error(err);process.exitCode=1});
