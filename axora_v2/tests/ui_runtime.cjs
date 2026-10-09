"use strict";
const fs=require("node:fs");
const vm=require("node:vm");
const assert=require("node:assert/strict");
const path=require("node:path");
const js=fs.readFileSync(path.join(__dirname,"../static/app.js"),"utf8");
const elements=new Map();
function element(id){
  if(!elements.has(id)) elements.set(id,{textContent:"",innerHTML:"",dataset:{},disabled:false,classList:{add(){},remove(){},toggle(){}},setAttribute(){},removeAttribute(){}});
  return elements.get(id);
}
const navNames=["dashboard","movements","forecasts","accounts","debts","import","settings"];
const nav=navNames.map(name=>({
  dataset:{page:name}, current:false,attrs:{},
  classList:{toggle(flag,on){if(flag==="active")this.owner.current=!!on}},
  setAttribute(k,v){this.attrs[k]=v},
  removeAttribute(k){delete this.attrs[k]}
}));
nav.forEach(n=>n.classList.owner=n);
const doc={querySelector(selector){return element(selector)},querySelectorAll(selector){return selector===".nav-link"?nav:[]},addEventListener(){}};
const ctx=vm.createContext({document:doc,window:{},console,Date,setTimeout,clearTimeout,Intl,URL,FormData,Number,String,Array,Math,Object,Set,Error});
vm.runInContext(js,ctx,{filename:"app.js"});
const summary={realized:395.8,located:395.8,discrepancy:0,to_receive:2000,to_pay:1000,projected:1395.8,debt_open:200,monthly:[],categories:[],next_forecasts:[],conciliation:100,goals:{emergency:100,investment:100,fixed:100,leisure:100}};
const dummy={
  movements:[{id:1,description:"Teste",classification:"ENTRADA",category:"ENTRADAS",competence:"10/2026",value:100,movement_date:"2026-10-09"}],
  forecasts:[{id:2,description:"Teste",due_date:"2026-10-10",type:"Entrada",status:"Não pago",competence:"10/2026",value:100,final_value:100}],
  accounts:[{id:3,name:"Conta teste",balance:200}],debts:[{id:4,description:"Dívida teste",status:"NÃO RENEGOCIADO",open_value:200,total_value:200}],
  settings:{net_income:2000,gross_income:2500,emergency_months:6,investment_pct:20,fixed_pct:50,leisure_pct:20,investment_multiple:250},summary
};
vm.runInContext("snapshot="+JSON.stringify(dummy)+"; me={display_name:'Teste',is_admin:false};",ctx);
for(const name of navNames){
  vm.runInContext("page="+JSON.stringify(name)+";render()",ctx);
  const html=element("#page-content").innerHTML;
  assert.ok(html.length>100,name+": conteudo vazio");
  assert.ok(nav.find(x=>x.dataset.page===name).current,name+": sem nav ativa");
  assert.equal(nav.filter(x=>x.current).length,1,name+": multiplas abas ativas");
  assert.ok(element("#page-title").textContent.length>0);
}
console.log("AXORA: sete paginas renderizadas e navegacao validada");

vm.runInContext('page="dashboard"',ctx);
const actions=vm.runInContext("actionButtons()",ctx);
assert.ok(actions.includes('data-action="export"'));
assert.ok(actions.includes('data-action="new-movement"'));
assert.ok(actions.includes('class="ui-icon"'),"Botoes devem utilizar iconografia vetorial uniforme");
vm.runInContext('page="movements"',ctx);
const newAction=vm.runInContext("actionButtons()",ctx);
assert.ok(newAction.includes('data-action="new"'));
assert.ok(newAction.includes('class="ui-icon"'));

for(const [value,expected] of [["loading","Atualizando"],["ready","Conectado"],["error","Falha ao atualizar"]]){
  vm.runInContext("updateSyncStatus("+JSON.stringify(value)+")",ctx);
  assert.equal(element("#top-sync-status").dataset.state,value);
  assert.equal(element("#sidebar-sync-status").dataset.state,value);
  assert.equal(element("#top-sync-label").textContent,expected);
}
vm.runInContext('page="settings";render()',ctx);
assert.ok(element("#page-content").innerHTML.includes("settings-connection-status"));
assert.ok(element("#page-content").innerHTML.includes("Falha ao atualizar informações financeiras"));
console.log("AXORA: iconografia comum e indicadores de sincronização validados");
