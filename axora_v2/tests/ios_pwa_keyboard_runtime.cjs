/* DOM mínimo: teclados móveis nunca devem diminuir a altura do login. */
"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const source=fs.readFileSync(require("node:path").join(__dirname,"../static/ios-pwa-stability.js"),"utf8");
const listeners={};
const props=new Map();
const root={clientHeight:844,style:{
  setProperty:(name,value)=>props.set(name,value),
  removeProperty:(name)=>props.delete(name)
}};
const doc={documentElement:root,activeElement:null};
const win={
  innerWidth:390,innerHeight:844,
  matchMedia:()=>({matches:true}),
  addEventListener:(name,fn)=>{listeners[name]=fn;},
  setTimeout:fn=>fn()
};
vm.runInNewContext(source,{document:doc,window:win,Math,Number});
const key="--axora-login-stage-height";
assert.equal(props.get(key),"844px","Initial iPhone viewport height must be saved.");
// iOS keyboard changes height (e.g. 844 -> 470) but not actual device width.
win.innerHeight=470;
doc.activeElement={id:"login-password"};
listeners.resize();
assert.equal(props.get(key),"844px","Keyboard must not reflow login card.");
doc.activeElement=null;
listeners.resize();
assert.equal(props.get(key),"844px","Keyboard close must not jitter login card.");
// Actual orientation change is allowed to rebuild the stage.
doc.activeElement={id:"login-password"};
win.innerWidth=844;
win.innerHeight=390;
root.clientHeight=390;
listeners.resize();
assert.equal(props.get(key),"844px","Resize while typing should not change stage until orientation settles.");
listeners.orientationchange();
assert.equal(props.get(key),"844px","Focused input prevents rotation recalculation.");
doc.activeElement=null;
listeners.orientationchange();
assert.equal(props.get(key),"390px","After focus ends, orientation updates stage.");
// Switching to desktop unsets iOS-only property.
win.innerWidth=1024;
win.innerHeight=768;
win.matchMedia=()=>({matches:false});
listeners.resize();
assert.equal(props.has(key),false,"Desktop must not keep mobile login sizing.");
console.log("iPhone PWA login resize test: OK");
