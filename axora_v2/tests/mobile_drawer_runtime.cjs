"use strict";
const fs=require("node:fs");
const vm=require("node:vm");
const assert=require("node:assert/strict");
const path=require("node:path");
const script=fs.readFileSync(path.join(__dirname,"../static/app.js"),"utf8");
function classes(initial=[]){
  const values=new Set(initial);
  return {add(...args){args.forEach(x=>values.add(x))},
          remove(...args){args.forEach(x=>values.delete(x))},
          contains(x){return values.has(x)},
          toggle(x){if(values.has(x)){values.delete(x);return false}values.add(x);return true}};
}
const elements={};
const doc={activeElement:null,body:{classList:classes()},querySelector(select){return elements[select]||null},
  querySelectorAll(select){if(select.startsWith("#sidebar button"))return [elements["#close-menu"],elements["#nav-first"],elements["#nav-last"]];return [];},
  addEventListener(){}};
const create=(key)=>elements[key]={
  classList:classes(),attrs:{},dataset:{},inert:false,
  setAttribute(name,value){this.attrs[name]=value},
  focus(){doc.activeElement=this},
  contains(target){return target===elements["#close-menu"]||target===elements["#nav-first"]||target===elements["#nav-last"];}
};
["#menu-toggle","#workspace","#sidebar","#sidebar-overlay","#close-menu","#nav-first","#nav-last"].forEach(create);
let mobile=true;
const ctx=vm.createContext({
  document:doc,window:{matchMedia(){return {matches:mobile}},scrollTo(){}},
  console,Date,setTimeout,clearTimeout,Intl,URL,FormData,Number,String,Array,Math,Object,Set,Error
});
vm.runInContext(script,ctx,{filename:"app.js"});
vm.runInContext("syncMenuTrigger()",ctx);
assert.equal(elements["#sidebar"].inert,true,"closed mobile menu must be inert");
assert.equal(elements["#sidebar"].attrs["aria-hidden"],"true");
assert.equal(elements["#menu-toggle"].attrs["aria-expanded"],"false");
vm.runInContext("showMenu()",ctx);
assert.equal(elements["#sidebar"].classList.contains("open"),true);
assert.equal(elements["#sidebar-overlay"].classList.contains("open"),true);
assert.equal(doc.body.classList.contains("menu-open"),true);
assert.equal(elements["#sidebar"].inert,false);
assert.equal(doc.activeElement,elements["#close-menu"]);
assert.equal(elements["#menu-toggle"].attrs["aria-expanded"],"true");

doc.activeElement=elements["#nav-last"];
let prevented=false;
ctx.keyEvent={key:"Tab",shiftKey:false,preventDefault(){prevented=true}};
vm.runInContext("trapMobileMenuFocus(keyEvent)",ctx);
assert.equal(prevented,true,"last menu item must trap focus");
assert.equal(doc.activeElement,elements["#close-menu"]);
doc.activeElement=elements["#close-menu"];prevented=false;
ctx.keyEvent={key:"Tab",shiftKey:true,preventDefault(){prevented=true}};
vm.runInContext("trapMobileMenuFocus(keyEvent)",ctx);
assert.equal(prevented,true);
assert.equal(doc.activeElement,elements["#nav-last"]);
vm.runInContext("hideMenu()",ctx);
assert.equal(elements["#sidebar"].classList.contains("open"),false);
assert.equal(elements["#sidebar-overlay"].classList.contains("open"),false);
assert.equal(doc.body.classList.contains("menu-open"),false);
assert.equal(elements["#sidebar"].inert,true);
assert.equal(doc.activeElement,elements["#menu-toggle"]);

mobile=false;
vm.runInContext("syncMenuTrigger()",ctx);
assert.equal(elements["#sidebar"].inert,false,"desktop navigation must remain accessible");
assert.equal(elements["#sidebar"].attrs["aria-hidden"],"false");
vm.runInContext("showMenu()",ctx);
assert.equal(elements["#workspace"].classList.contains("sidebar-collapsed"),true);
assert.equal(elements["#sidebar-overlay"].classList.contains("open"),false);
console.log("AXORA mobile: overlay, clickable menu, focus trap, Escape-compatible hide and desktop fallback OK");
