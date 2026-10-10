/* AXORA 2.0 — Interface nativa, sem runtime Streamlit nem bibliotecas de UI externas. */
"use strict";
const $ = (selector, root=document) => root.querySelector(selector);
const $$ = (selector, root=document) => [...root.querySelectorAll(selector)];
const esc = v => String(v ?? "").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const money = v => Number(v || 0).toLocaleString("pt-BR",{style:"currency",currency:"BRL"});
const num = v => Number(v || 0);
const metricIcons={
  trend:'<path d="m3 17 6-6 4 4 8-9"/><path d="M15 6h6v6"/>',
  wallet:'<rect x="3" y="6" width="18" height="15" rx="2"/><path d="M3 10h18M16 15h2"/>',
  receive:'<path d="M12 3v14m-5-5 5 5 5-5"/><path d="M4 20h16"/>',
  pay:'<path d="M12 20V6m-5 5 5-5 5 5"/><path d="M4 3h16"/>',
  projection:'<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 16v-4M12 16V8M17 16v-6"/>',
  debt:'<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6M9 12h6M9 16h3"/>'
};
function metricIcon(name){
  return '<svg viewBox="0 0 24 24" aria-hidden="true">'+(metricIcons[name]||metricIcons.wallet)+'</svg>';
}
// Ícones lineares compartilhados — a mesma linguagem em todas as páginas.
const interfaceIconPaths={
  plus:'<path d="M12 5v14M5 12h14"/>',
  download:'<path d="M12 3v12m-5-5 5 5 5-5"/><path d="M5 18v3h14v-3"/>',
  edit:'<path d="M12 20h9"/><path d="m16.5 3.5 4 4L9 19H5v-4L16.5 3.5Z"/>',
  trash:'<path d="M3 6h18M8 6V4h8v2M6 6l1 15h10l1-15M10 11v6m4-6v6"/>',
  filter:'<path d="M4 7h16M7 12h10M10 17h4"/>',
  reset:'<path d="M3 11a9 9 0 1 1 3.2 6.9"/><path d="M3 4v7h7"/>',
  shield:'<path d="m12 22 8-4V6l-8-4-8 4v12l8 4Z"/><path d="m8.5 12 2.2 2.2 4.7-4.7"/>',
  check:'<path d="m5 12 4 4L19 6"/>'
};
function interfaceIcon(name){
  return '<svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true">'+(interfaceIconPaths[name]||interfaceIconPaths.plus)+'</svg>';
}

const today = () => new Date().toLocaleDateString("en-CA");
const comp = () => {const d=new Date();return String(d.getMonth()+1).padStart(2,"0")+"/"+d.getFullYear()};
const dateBR = v => v ? String(v).substring(0,10).split("-").reverse().join("/") : "—";
const labels = {dashboard:"Visão financeira",movements:"Movimentações",forecasts:"Contas e previsões",accounts:"Contas e saldos",debts:"Dívidas",import:"Importar / Exportar",settings:"Configurações"};
const subtitles = {dashboard:"Controle o seu presente. Planeje o seu próximo passo.",movements:"Receitas e despesas realizadas, sem misturar previsões.",forecasts:"Acompanhe os compromissos e recebimentos futuros.",accounts:"Saiba exatamente onde está o seu dinheiro.",debts:"Organize pagamentos, renegociações e saldos em aberto.",import:"Leve sua planilha para o AXORA com segurança.",settings:"Personalize seu perfil e defina suas metas financeiras."};
const meta = {
  movements: [
    ["description","Descrição","text",true],["value","Valor (R$)","number",true],
    ["classification","Classificação","select:SAÍDA|ENTRADA",true],["category","Categoria","text"],
    ["competence","Competência (MM/AAAA)","text"],["movement_date","Data","date"],
    ["allocation_value","Valor do rateio","number"],["fixed_variable","Fixo / Variável","select:FIXO|VARIÁVEL"]
  ],
  forecasts: [
    ["description","Descrição","text",true],["due_date","Vencimento","date"],["value","Valor (R$)","number",true],
    ["adjustment","Desconto / juros","number"],["type","Tipo","select:Saída|Entrada",true],
    ["status","Status","select:Não pago|Pago"],["category","Categoria","text"],
    ["competence","Competência","text"],["simulate_payment","Incluir em simulação","checkbox"]
  ],
  accounts: [["name","Conta / Local","text",true],["balance","Saldo (R$)","number",true]],
  debts: [
    ["description","Descrição","text",true],["total_value","Valor original","number"],["status","Status","select:NÃO RENEGOCIADO|RENEGOCIADO"],
    ["total_installments","Total de parcelas","integer"],["paid_installments","Parcelas pagas","integer"],
    ["installment_value","Valor da parcela","number"],["open_value","Valor em aberto","number"]
  ]
};
const columns = {
  movements:[["movement_date","Data","date"],["description","Descrição"],["value","Valor","money"],["classification","Tipo","status"],["category","Categoria"],["competence","Competência"],["fixed_variable","Natureza"],["allocation_value","Rateio","money"]],
  forecasts:[["due_date","Vencimento","date"],["description","Descrição"],["final_value","Valor final","money"],["type","Tipo","status"],["status","Status","status"],["category","Categoria"],["competence","Competência"],["simulate_payment","Simular","bool"]],
  accounts:[["name","Conta / local"],["balance","Saldo","money"]],
  debts:[["description","Descrição"],["status","Situação","status"],["total_value","Original","money"],["total_installments","Parcelas"],["paid_installments","Pagas"],["installment_value","Parcela","money"],["open_value","Em aberto","money"]]
};
let me=null,snapshot=null,page="dashboard",filters={},excelFile=null,toastTimeout=0;
let institutionalBrand={has_logo:false,updated_at:null};
let syncStatus="loading";
let institutionalPreviewUrl=null;
async function api(path,opts={}) {
  const headers={...(opts.headers||{})};
  if(me && opts.method && opts.method !== "GET") headers["X-CSRF-Token"]=me.csrf;
  if(opts.body && !(opts.body instanceof FormData)) headers["Content-Type"]="application/json";
  let response;
  try {response=await fetch(path,{...opts,headers,credentials:"same-origin",cache:"no-store"})}
  catch {throw Error("Não foi possível conectar ao servidor. Verifique sua internet.")}
  if(!response.ok) {
    let err;try{err=(await response.json()).detail}catch{err="Falha inesperada no servidor."}
    if(response.status===401 && !path.endsWith("/login")) {logoutVisual();throw Error("Sua sessão expirou. Entre novamente.")}
    throw Error(typeof err==="string"?err:"Não foi possível concluir a operação.");
  }
  return response.headers.get("content-type")?.includes("application/json")?response.json():response;
}
function applyInstitutionalBrand(){
  const configured=Boolean(institutionalBrand.has_logo);
  const url="/api/branding/institutional/image?v="+encodeURIComponent(institutionalBrand.updated_at||"");
  document.querySelectorAll("[data-institutional-logo]").forEach(image=>{
    image.hidden=!configured;
    if(configured && image.getAttribute("src")!==url)image.setAttribute("src",url);
    if(!configured)image.removeAttribute("src");
  });
  document.querySelectorAll("[data-institutional-fallback]").forEach(label=>{label.hidden=configured});
  const status=$("#institutional-logo-status");
  if(status)status.textContent=configured?"Assinatura institucional personalizada ativa no login e no rodapé.":"Nenhuma imagem enviada. Por enquanto, o aplicativo utiliza apenas a assinatura textual Nexon Labs.";
}
async function loadInstitutionalBrand(){
  institutionalBrand=await api("/api/branding/institutional");
  applyInstitutionalBrand();
}
function releaseInstitutionalPreview(){
  if(institutionalPreviewUrl){URL.revokeObjectURL(institutionalPreviewUrl);institutionalPreviewUrl=null}
}
function showToast(message,error=false){const t=$("#toast");t.textContent=message;t.className="toast show"+(error?" error":"");clearTimeout(toastTimeout);toastTimeout=setTimeout(()=>t.className="toast",4300)}
function logoutVisual(){me=null;snapshot=null;$("#workspace").classList.add("hidden");$("#login").classList.remove("hidden");$("#login-password").value="";$("#login-password").focus()}
function enterVisual(){ $("#login").classList.add("hidden");$("#workspace").classList.remove("hidden");$("#user-name").textContent=me.display_name;const a=$("#avatar");a.replaceChildren();if(me.avatar_data_uri){const i=document.createElement("img");i.src=me.avatar_data_uri;i.alt="";a.append(i)}else a.textContent=(me.display_name||"A")[0].toUpperCase()}
async function start(){try{me=await api("/api/me");enterVisual();await refresh()}catch{logoutVisual()}}
function updateSyncStatus(status){
  syncStatus=status;
  const timestamp=new Date().toLocaleTimeString("pt-BR",{hour:"2-digit",minute:"2-digit"});
  const text=status==="ready"?"Conectado":status==="loading"?"Atualizando":"Falha ao atualizar";
  const sidebar=status==="ready"?"Dados sincronizados":status==="loading"?"Atualizando dados":"Verifique a conexão";
  const description=status==="ready"?"Atualizado às "+timestamp:status==="loading"?"Consultando base financeira…":"Última atualização não concluída";
  const top=$("#top-sync-status"),side=$("#sidebar-sync-status");
  if(top){top.dataset.state=status;top.title=status==="ready"?description:description}
  if(side)side.dataset.state=status;
  if($("#top-sync-label"))$("#top-sync-label").textContent=text;
  if($("#sidebar-sync-label"))$("#sidebar-sync-label").textContent=sidebar;
  if($("#sidebar-sync-time"))$("#sidebar-sync-time").textContent=description;
  const settings=$("#settings-connection-status");
  if(settings)settings.textContent=status==="ready"?"Dados financeiros sincronizados":status==="loading"?"Atualizando informações financeiras":"Falha ao atualizar informações financeiras";
}
async function refresh(){
  const button=$("#refresh");
  if(button)button.disabled=true;
  updateSyncStatus("loading");
  try{
    const latest=await api("/api/snapshot");
    snapshot=latest;
    render();
    updateSyncStatus("ready");
  }catch(error){
    updateSyncStatus("error");
    throw error;
  }finally{
    if(button)button.disabled=false;
  }
}
function go(next){page=next;filters={};hideMenu();render();if(next==="settings"&&me?.is_admin)loadUsers();window.scrollTo({top:0,behavior:"smooth"})}
function syncMenuTrigger(){
  const button=$("#menu-toggle"),mobile=window.matchMedia("(max-width:850px)").matches;
  const sidebar=$("#sidebar");
  const collapsed=$("#workspace").classList.contains("sidebar-collapsed");
  const open=sidebar.classList.contains("open");
  button.setAttribute("aria-expanded",String(mobile?open:!collapsed));
  button.setAttribute("aria-label",mobile?(open?"Menu aberto":"Abrir menu"):collapsed?"Expandir menu":"Recolher menu");
  // Fora do mobile, a barra lateral permanece navegável.
  sidebar.inert=mobile&&!open;
  sidebar.setAttribute("aria-hidden",String(mobile&&!open));
}
function showMenu(){
  if(window.matchMedia("(max-width:850px)").matches){
    $("#sidebar").classList.add("open");
    $("#sidebar-overlay").classList.add("open");
    document.body.classList.add("menu-open");
    syncMenuTrigger();
    $("#close-menu").focus({preventScroll:true});
  }else{
    $("#workspace").classList.toggle("sidebar-collapsed");
    syncMenuTrigger();
  }
}
function hideMenu(){
  const wasOpen=$("#sidebar").classList.contains("open");
  $("#sidebar").classList.remove("open");
  $("#sidebar-overlay").classList.remove("open");
  document.body.classList.remove("menu-open");
  syncMenuTrigger();
  if(wasOpen&&window.matchMedia("(max-width:850px)").matches){
    $("#menu-toggle").focus({preventScroll:true});
  }
}
function trapMobileMenuFocus(e){
  if(e.key!=="Tab"||!$("#sidebar").classList.contains("open"))return;
  const items=$$("#sidebar button:not([disabled]), #sidebar a[href], #sidebar [tabindex]:not([tabindex='-1'])");
  if(!items.length)return;
  const first=items[0],last=items[items.length-1],active=document.activeElement;
  if(e.shiftKey&&(active===first||!$("#sidebar").contains(active))){
    e.preventDefault();last.focus();
  }else if(!e.shiftKey&&(active===last||!$("#sidebar").contains(active))){
    e.preventDefault();first.focus();
  }
}
function actionButtons(){
  if(meta[page])return '<button class="btn primary btn-strong" data-action="new">'+interfaceIcon("plus")+'<span>Novo registro</span></button>';
  if(page==="dashboard")return '<button class="btn ghost btn-secondary" data-action="export">'+interfaceIcon("download")+'<span>Exportar Excel</span></button><button class="btn primary btn-strong" data-action="new-movement">'+interfaceIcon("plus")+'<span>Movimentação</span></button>';
  if(page==="import")return '<button class="btn ghost btn-secondary" data-action="export">'+interfaceIcon("download")+'<span>Exportar Excel</span></button>';
  return "";
}
function render(){
  if(!snapshot)return;
  $("#page-title").textContent=labels[page];$("#page-subtitle").textContent=subtitles[page];$("#crumb-current").textContent=labels[page].toUpperCase();$("#page-actions").innerHTML=actionButtons();
  $$(".nav-link").forEach(x=>{const active=x.dataset.page===page;x.classList.toggle("active",active);if(active)x.setAttribute("aria-current","page");else x.removeAttribute("aria-current")});
  const body=$("#page-content");
  body.innerHTML=page==="dashboard"?dashboard():meta[page]?modulePage(page):page==="import"?importPage():settingsPage();
  applyInstitutionalBrand();
  if(typeof applyBrandKit==="function")applyBrandKit();
}
function metric(label,value,hint,icon,tone=""){return '<div class="metric-card '+tone+'"><div class="metric-label">'+esc(label)+'<span class="metric-icon">'+metricIcon(icon)+'</span></div><div class="metric-value">'+money(value)+'</div><div class="metric-meta">'+esc(hint)+'</div></div>'}
function panel(title,desc,content){return '<section class="panel"><div class="panel-heading"><div><h2>'+title+'</h2><p>'+desc+'</p></div></div>'+content+'</section>'}
function dashboard(){
  const x=snapshot.summary,s=snapshot.settings;
  let cards=[
    metric("Saldo realizado",x.realized,"Receitas menos despesas","trend"),
    metric("Saldo localizado",x.located,"Diferença "+money(x.discrepancy),"wallet","info"),
    metric("A receber",x.to_receive,"Previsões pendentes","receive"),
    metric("A pagar",x.to_pay,"Compromissos futuros","pay","negative"),
    metric("Saldo projetado",x.projected,"Realizado + previsões","projection","info"),
    metric("Dívida em aberto",x.debt_open,"Passivo financeiro","debt","negative")
  ].join("");
  let forecasts=table(["Vencimento","Descrição","Tipo","Valor","Status"],x.next_forecasts.map(f=>[
    dateBR(f.due_date),f.description,f.type,money(f.final_value),f.status
  ]),false);
  let goals=Number(s.net_income)>0?'<div class="goal-strip">'+[
    ["Reserva de emergência",x.goals.emergency],["Investimento mensal",x.goals.investment],
    ["Contas fixas",x.goals.fixed],["Lazer",x.goals.leisure]
  ].map(([l,v])=>'<div class="goal-item"><small>'+esc(l)+'</small><b>'+money(v)+'</b></div>').join("")+'</div>':'<div class="empty-state">Defina sua renda líquida em Configurações para visualizar as metas.</div>';
  let reconciliation='<div class="conciliation-big">'+num(x.conciliation).toFixed(0)+'%</div><p class="panel-copy">Nível estimado de conciliação</p><progress class="progress-native" value="'+num(x.conciliation)+'" max="100" aria-label="Conciliação dos saldos"></progress><ul class="checklist"><li>Realizado separado do previsto</li><li>Saldos comparados com o sistema</li><li>Divergência: '+money(x.discrepancy)+'</li></ul>';
  const html='<div class="metric-grid">'+cards+'</div><div class="grid-two">'+
    panel("Evolução financeira mensal","Receitas, despesas e saldo a partir de julho de 2026.",chartMonthly(x.monthly))+
    panel("Despesas por categoria","Distribuição das saídas registradas.",chartDonut(x.categories))+'</div><div class="grid-two">'+
    panel("Próximas contas e previsões","Agenda financeira para acompanhamento imediato.",forecasts)+
    panel("Conciliação de saldo","Conferência do saldo calculado e localizado.",reconciliation)+'</div>'+
    panel("Suas metas financeiras","Planejamento baseado na renda líquida configurada.",goals);
  return html;
}
function chartMonthly(months){
  if(!months?.length || !months.some(x=>num(x.receipts)||num(x.expenses)))return '<div class="empty-state"><b>Sem movimentações no período</b>O gráfico aparecerá ao registrar receitas e despesas.</div>';
  const w=640,h=220,pad=30,step=(w-2*pad)/months.length,max=Math.max(1,...months.map(x=>num(x.receipts)),...months.map(x=>num(x.expenses)))*1.14;
  let result='<div class="chart-key"><span><i class="inc"></i>Receitas</span><span><i class="out"></i>Despesas</span><span><i class="saldo"></i>Saldo</span></div><svg class="chart-svg" viewBox="0 0 640 230" role="img" aria-label="Gráfico mensal de receitas, despesas e saldo">';
  for(let n=0;n<4;n++){let y=15+n*53;result+='<line class="svg-grid" x1="25" x2="630" y1="'+y+'" y2="'+y+'"/>'}
  let pts=[];
  months.forEach((m,i)=>{
    const x=pad+i*step+step*.2, base=h-20, a=Math.max(0,num(m.receipts)/max)*(h-40),b=Math.max(0,num(m.expenses)/max)*(h-40);
    result+='<rect x="'+x+'" y="'+(base-a)+'" width="'+(step*.22)+'" height="'+a+'" fill="#22b99d" rx="3"><title>Receitas '+esc(m.competence)+': '+esc(money(m.receipts))+'</title></rect>';
    result+='<rect x="'+(x+step*.25)+'" y="'+(base-b)+'" width="'+(step*.22)+'" height="'+b+'" fill="#34597f" rx="3"><title>Despesas '+esc(m.competence)+': '+esc(money(m.expenses))+'</title></rect>';
    result+='<text class="svg-label" x="'+(x+step*.22)+'" y="222" text-anchor="middle">'+esc(m.competence)+'</text>';
    pts.push((x+step*.22)+","+(base-Math.max(0,num(m.balance))/max*(h-40)));
  });
  result+='<polyline points="'+pts.join(" ")+'" fill="none" stroke="#72c9d2" stroke-width="2.5"/>';
  result+='</svg>';return result;
}
function chartDonut(cats){
  if(!cats?.length)return '<div class="empty-state"><b>Nenhuma despesa cadastrada</b>As categorias aparecerão após as movimentações.</div>';
  const colors=["#14B8A6","#1C7EB0","#7DD3FC","#4779B9","#83B8CE","#0E4D6B","#B8DAD7"],total=cats.reduce((x,y)=>x+num(y.value),0);
  let offset=0;const arcs=cats.map((c,i)=>{const share=num(c.value)/total*100;const svg='<circle cx="90" cy="90" r="70" fill="none" stroke="'+colors[i%colors.length]+'" stroke-width="25" stroke-dasharray="'+share+' '+(100-share)+'" stroke-dashoffset="'+(-offset)+'" pathLength="100" transform="rotate(-90 90 90)"><title>'+esc(c.name)+': '+esc(money(c.value))+'</title></circle>';offset+=share;return svg}).join("");
  return '<div class="donut-container"><svg class="donut-svg" viewBox="0 0 180 180" role="img" aria-label="Distribuição das despesas">'+arcs+'<circle cx="90" cy="90" r="48" fill="#fff"/><text x="90" y="84" text-anchor="middle" fill="#8798a8" font-size="10">DESPESAS</text><text x="90" y="106" text-anchor="middle" font-size="12" font-weight="750" fill="#223853">'+esc(money(total))+'</text></svg><div class="donut-legend">'+cats.map((c,i)=>'<div class="donut-legend-line"><span><i style="background:'+colors[i%colors.length]+'"></i>'+esc(c.name)+'</span><b>'+money(c.value)+'</b></div>').join("")+'</div></div>';
}
function displayTableCell(cell,heading){
  const label=String(cell??"");
  if(["Tipo","Status","Situação","Natureza","Simular"].includes(heading)){
    const negative=/^(saída|não pago|não renegociado|não)$/i.test(label.trim());
    return '<span class="status-badge'+(negative?' red':'')+'">'+esc(label)+'</span>';
  }
  return esc(label);
}
function table(headings,rows,actions=false,kind=""){
  if(!rows.length)return '<div class="empty-state"><b>Nenhum registro encontrado</b>Cadastre dados ou ajuste os filtros para continuar.</div>';
  return '<div class="table-wrap"><table class="data-table"><thead><tr>'+headings.map(h=>'<th scope="col">'+esc(h)+'</th>').join("")+(actions?'<th scope="col">Ações</th>':'')+'</tr></thead><tbody>'+
    rows.map((cols,i)=>'<tr>'+cols.map((cell,j)=>'<td data-label="'+esc(headings[j])+'" title="'+esc(cell)+'">'+displayTableCell(cell,headings[j])+'</td>').join("")+(actions?'<td data-label="Ações"><div class="table-actions"><button class="mini-btn" data-action="edit" data-kind="'+kind+'" data-id="'+esc(actions[i])+'" aria-label="Editar registro">'+interfaceIcon("edit")+'<span>Editar</span></button><button class="mini-btn danger" data-action="delete" data-kind="'+kind+'" data-id="'+esc(actions[i])+'" aria-label="Excluir registro">'+interfaceIcon("trash")+'<span>Excluir</span></button></div></td>':'')+'</tr>').join("")+'</tbody></table></div>';
}
function formatCell(row,key,type){
  const v=row[key];if(type==="money")return money(v);if(type==="date")return dateBR(v);if(type==="bool")return v?"Sim":"Não";return String(v??"—");
}
function filteredRows(kind){
  let rows=[...(snapshot[kind]||[])],f=filters;
  if(f.search){let q=f.search.toLocaleLowerCase("pt-BR");rows=rows.filter(r=>Object.values(r).some(v=>String(v??"").toLocaleLowerCase("pt-BR").includes(q)))}
  if(f.competence)rows=rows.filter(r=>r.competence===f.competence);
  if(f.classification)rows=rows.filter(r=>(r.classification||r.type)===f.classification);
  if(f.status)rows=rows.filter(r=>r.status===f.status);
  if(f.category)rows=rows.filter(r=>r.category===f.category);
  return rows;
}
function uniq(kind,field){return [...new Set(snapshot[kind].map(r=>r[field]).filter(Boolean))].sort()}
function optionFilter(key,label,choices){return '<select data-filter="'+key+'" aria-label="'+esc(label)+'"><option value="">'+esc(label)+'</option>'+choices.map(v=>'<option value="'+esc(v)+'" '+(filters[key]===v?"selected":"")+'>'+esc(v)+'</option>').join("")+'</select>'}
function moduleStats(kind,rows){
  let values;
  if(kind==="movements"){let a=rows.filter(x=>x.classification==="ENTRADA").reduce((s,x)=>s+num(x.value),0),b=rows.filter(x=>x.classification!=="ENTRADA").reduce((s,x)=>s+num(x.value),0);values=[["Entradas",a],["Saídas",b],["Resultado",a-b]]}
  else if(kind==="forecasts"){let p=rows.filter(x=>!["pago","recebido","sim"].includes(String(x.status||"").toLowerCase())),a=p.filter(x=>x.type==="Entrada").reduce((s,x)=>s+num(x.final_value),0),b=p.filter(x=>x.type==="Saída").reduce((s,x)=>s+num(x.final_value),0);values=[["A receber",a],["A pagar",b],["Impacto líquido",a-b]]}
  else if(kind==="accounts"){values=[["Saldo do sistema",snapshot.summary.realized],["Saldo informado",snapshot.summary.located],["Divergência",snapshot.summary.discrepancy]]}
  else {let ren=rows.filter(x=>x.status==="RENEGOCIADO").reduce((s,x)=>s+num(x.open_value),0),other=rows.filter(x=>x.status!=="RENEGOCIADO").reduce((s,x)=>s+num(x.open_value),0);values=[["Total em aberto",ren+other],["Renegociado",ren],["Não renegociado",other]]}
  return '<div class="metric-grid">'+values.map(([l,v],i)=>metric(l,v,"Valores dos registros",["projection","trend","wallet"][i],i===1?"info":"")).join("")+'</div>';
}
function modulePage(kind){
  const rows=filteredRows(kind),data=columns[kind], filtersHtml='<input class="search-box" data-filter="search" placeholder="Pesquisar registros..." aria-label="Pesquisar" value="'+esc(filters.search||"")+'">'+
    ((kind==="movements"||kind==="forecasts")?optionFilter("competence","Todas competências",uniq(kind,"competence")):"")+
    (kind==="movements"?optionFilter("classification","Todas classificações",["ENTRADA","SAÍDA"]):"")+
    (kind==="forecasts"?optionFilter("classification","Todos os tipos",["Entrada","Saída"])+optionFilter("status","Todos os status",["Não pago","Pago"]):"")+
    (kind==="movements"?optionFilter("category","Todas categorias",uniq(kind,"category")):"");
  return '<div id="module-stats">'+moduleStats(kind,rows)+'</div><section class="panel table-panel"><div class="table-tools"><div class="filters">'+filtersHtml+'</div><button class="btn ghost small btn-clear" data-action="clear-filters">'+interfaceIcon("reset")+'<span>Limpar filtros</span></button></div><div id="table-body">'+moduleTable(kind,rows)+'</div></section>';
}
function moduleTable(kind,rows){
  const cols=columns[kind],visible=rows.slice(0,150);
  const rendered=visible.map(row=>cols.map(([key,label,type])=>formatCell(row,key,type)));
  return table(cols.map(x=>x[1]),rendered,visible.map(x=>x.id),kind)+'<div class="table-count">'+rows.length+' registro(s) encontrados'+(rows.length>150?" · exibindo os 150 primeiros; refine sua pesquisa":"")+'</div>';
}
function updateFiltered(){if(!meta[page])return;let rows=filteredRows(page);$("#module-stats").innerHTML=moduleStats(page,rows);$("#table-body").innerHTML=moduleTable(page,rows)}
function defaultValue(kind,key){if(key==="competence")return comp();if(key==="due_date"||key==="movement_date")return today();if(key==="classification")return "SAÍDA";if(key==="type")return "Saída";if(key==="status")return kind==="forecasts"?"Não pago":"NÃO RENEGOCIADO";if(key==="fixed_variable")return "FIXO";if(key==="category"&&kind==="movements")return "CONTAS FIXAS";return ""}
function editor(kind,id){
  let r=id?snapshot[kind].find(row=>Number(row.id)===Number(id)):null;
  $("#editor-title").textContent=(r?"Editar ":"Adicionar ")+labels[kind].toLowerCase();
  const form=$("#editor-form");form.dataset.kind=kind;form.dataset.id=id||"";
  $("#editor-fields").innerHTML=meta[kind].map(([key,title,type,required])=>{
    const current=r?r[key]:defaultValue(kind,key);
    if(type==="checkbox")return '<div class="field checkbox full"><input id="fld-'+key+'" name="'+key+'" type="checkbox" '+(current?"checked":"")+'><label for="fld-'+key+'">'+esc(title)+'</label></div>';
    let entry;
    if(type.startsWith("select:"))entry='<select id="fld-'+key+'" name="'+key+'">'+type.slice(7).split("|").map(s=>'<option value="'+esc(s)+'" '+(s===String(current)?"selected":"")+'>'+esc(s)+'</option>').join("")+'</select>';
    else entry='<input id="fld-'+key+'" name="'+key+'" type="'+(type==="integer"?"number":type==="number"?"number":type==="date"?"date":"text")+'" '+(type==="number"?'step="0.01"':type==="integer"?'step="1" min="0"':"")+' '+(required?"required":"")+' value="'+esc(current??"")+'" />';
    return '<div class="field"><label for="fld-'+key+'">'+esc(title)+'</label>'+entry+'</div>';
  }).join("");
  $("#editor-dialog").showModal();
}
async function saveEditor(e){
  e.preventDefault();const form=e.currentTarget,kind=form.dataset.kind,id=form.dataset.id;
  const data={};for(const [key,label,type] of meta[kind]){const element=form.elements.namedItem(key);data[key]=type==="checkbox"?element.checked:type==="number"||type==="integer"?Number(element.value||0):element.value}
  try{await api("/api/rows/"+kind+(id?"/"+id:""),{method:id?"PATCH":"POST",body:JSON.stringify(data)});$("#editor-dialog").close();await refresh();showToast("Registro salvo com sucesso.")}catch(err){showToast(err.message,true)}
}
function importPage(){return '<div class="stack">'+panel("Importar planilha","Modelo ACOMPANHAMENTOS.xlsx com as quatro abas financeiras obrigatórias.",'<div class="notice warning"><b>Proteção dos dados:</b> o AXORA não substitui registros existentes. A carga inicial só funciona se todas as quatro tabelas estiverem vazias. Faça backup antes de importar.</div><div class="upload-box"><b>Selecione um arquivo .xlsx</b><p>Movimentações, previsões, dinheiro e demais dívidas.</p><input type="file" id="excel-upload" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"></div><div id="import-preview"></div><div class="page-actions import-actions"><button class="btn ghost" data-action="preview-import">'+interfaceIcon("check")+'<span>Conferir planilha</span></button><button class="btn primary" data-action="commit-import">'+interfaceIcon("plus")+'<span>Importar dados</span></button></div>')+
   panel("Exportar dados","Baixe as quatro bases financeiras em um único arquivo Excel.",'<p class="panel-copy">Exportação de movimentações, previsões, contas e dívidas. Recomendado antes de mudanças importantes.</p><button class="btn primary" data-action="export">'+interfaceIcon("download")+'<span>Exportar Excel</span></button>')+'</div>'}
async function loadUsers(){try{const users=await api("/api/users");const el=$("#users-table");if(el)el.innerHTML=table(["Nome","Perfil","Situação"],users.map(u=>[u.display_name,u.is_admin?"Administrador":"Usuário",u.is_active?"Ativo":"Inativo"]),false)}catch(e){showToast(e.message,true)}}
function settingsPage(){
  const s=snapshot.settings;
  let goalInputs=[["gross_income","Renda bruta mensal (R$)"],["net_income","Renda líquida mensal (R$)"],["emergency_months","Reserva de emergência (meses)"],["investment_pct","Investimento mensal (%)"],["fixed_pct","Contas fixas (%)"],["leisure_pct","Lazer (%)"],["investment_multiple","Meta de patrimônio (x renda)"]];
  const goalForm='<form id="goal-form" class="settings-form">'+goalInputs.map(([k,l])=>'<div class="field"><label for="setting-'+k+'">'+esc(l)+'</label><input id="setting-'+k+'" name="'+k+'" type="number" min="0" step="0.01" value="'+esc(s[k])+'" required></div>').join("")+'<button type="submit" class="btn primary">Salvar metas</button></form>';
  let profile='<div class="notice">O AXORA identifica o usuário pela senha. Todos os usuários cadastrados nesta versão compartilham a mesma base financeira.</div><form id="profile-form" class="settings-form"><div class="field"><label for="profile-name">Nome exibido</label><input id="profile-name" name="display_name" maxlength="40" value="'+esc(me.display_name)+'" required></div><button type="submit" class="btn primary">Atualizar nome</button></form><hr><div class="field"><label for="avatar-upload">Foto de perfil · PNG ou JPEG (até 15 MB)</label><input id="avatar-upload" type="file" accept="image/png,image/jpeg"></div><div class="page-actions"><button class="btn ghost small" data-action="upload-avatar">Atualizar foto</button><button class="btn danger small" data-action="delete-avatar">Remover foto</button></div><br><button class="btn ghost" data-action="logout">Sair / trocar usuário</button>';
  let adminForm='<div class="notice warning">Atenção: novos usuários poderão visualizar e alterar a <b>mesma base financeira</b>. Não há isolamento por usuário nesta versão.</div><form id="new-user-form" class="settings-form"><div class="field"><label>Nome</label><input name="display_name" required maxlength="40"></div><div class="field"><label>Senha exclusiva (mínimo 12 caracteres)</label><input name="password" type="password" minlength="12" required></div><div class="field checkbox full"><input id="share-ack" name="share_ack" type="checkbox" required><label for="share-ack">Confirmo que o usuário terá acesso à base financeira compartilhada</label></div><button type="submit" class="btn primary">Cadastrar usuário</button></form><div id="users-table" class="table-wrap"></div>';
  const signaturePanel='<div class="institutional-brand-editor"><div class="institutional-preview"><img data-institutional-logo alt="Prévia da assinatura Nexon Labs" width="220" height="60" hidden><span class="institutional-brand-fallback" data-institutional-fallback>by Nexon Labs</span></div><p id="institutional-logo-status" class="panel-copy"></p>'+
    (me.is_admin?'<div class="field"><label for="institutional-logo-upload">Enviar logo institucional · PNG, JPG ou WebP (até 5 MB)</label><input id="institutional-logo-upload" type="file" accept="image/png,image/jpeg,image/webp"></div><div class="page-actions"><button class="btn primary" type="button" data-action="upload-institutional-logo">Salvar assinatura</button><button class="btn ghost" type="button" data-action="delete-institutional-logo">Restaurar padrão</button></div>':'<div class="notice">Somente administradores podem alterar a identidade institucional.</div>')+'</div>';
  const multiuserPanel='<div class="notice warning"><b>Base multiusuário em preparação:</b> as contas atuais ainda compartilham os mesmos dados financeiros. O isolamento por espaços de trabalho será ativado somente após proteger todas as operações. Não cadastre usuários que precisem de dados privados nesta fase.</div><div class="workspace-roles"><span>Proprietário</span><span>Administrador</span><span>Editor</span><span>Leitor</span></div><p class="panel-copy">A próxima etapa permitirá base privada por usuário e compartilhamento autorizado de espaços financeiros.</p>';
  return '<div class="settings-grid"><div class="stack">'+panel("Meu perfil","Personalize a identificação associada à sua senha.",profile)+panel("Padrão visual de logos","Logo principal, versão compacta, ícone e favicon, com download PNG.",typeof brandKitPanel==="function"?brandKitPanel():"")+panel("Identidade institucional","Assinatura institucional Nexon Labs usada no login e no rodapé.",signaturePanel)+panel("Base multiusuário","Estrutura de espaços e níveis de acesso — fase de preparação.",multiuserPanel)+(me.is_admin?panel("Usuários e permissões","Criação de contas e acesso à base compartilhada.",adminForm):"")+'</div><div class="stack">'+panel("Metas financeiras","Defina renda, reserva, percentuais e patrimônio.",goalForm)+panel("Conectividade","Informações sobre os serviços do AXORA.",'<div class="notice"><span class="online-dot"></span> <span id="settings-connection-status">'+(syncStatus==="ready"?"Dados financeiros sincronizados":syncStatus==="loading"?"Atualizando informações financeiras":"Falha ao atualizar informações financeiras")+'</span> · FastAPI · Hostinger</div><p class="panel-copy">AXORA by Nexon Labs. A versão web não utiliza a interface ou infraestrutura Streamlit.</p>')+'</div></div>';
}
async function doExport(){try{const res=await api("/api/export");const blob=await res.blob();const url=URL.createObjectURL(blob);const a=document.createElement("a");a.href=url;a.download="axora_export.xlsx";document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),2000);showToast("Planilha exportada.")}catch(e){showToast(e.message,true)}}
async function uploadExcel(endpoint){
  if(!excelFile)throw Error("Selecione a planilha Excel.");
  const form=new FormData();form.append("file",excelFile);
  return api(endpoint,{method:"POST",body:form});
}
async function importAction(action){
  try{
    if(action==="preview-import"){
      const data=await uploadExcel("/api/import/preview");
      $("#import-preview").innerHTML='<div class="upload-counts">'+Object.entries(data.counts).map(([k,v])=>'<span>'+esc(labels[k])+': <b>'+esc(v)+'</b></span>').join("")+'</div>';
      showToast("Conferência concluída. Nenhum dado foi gravado.");
    }else{
      if(!excelFile)throw Error("Selecione a planilha primeiro.");
      if(!confirm("Confirma a importação? A operação só é permitida com as quatro tabelas vazias. Faça backup antes de continuar."))return;
      const data=await uploadExcel("/api/import/commit");showToast("Importação finalizada.");excelFile=null;await refresh();
    }
  }catch(e){showToast(e.message,true)}
}
function bind(){
  $("#login-form").addEventListener("submit",async e=>{e.preventDefault();$("#login-error").textContent="";const btn=e.currentTarget.querySelector("button[type=submit]");btn.disabled=true;try{await api("/api/login",{method:"POST",body:JSON.stringify({password:$("#login-password").value})});me=await api("/api/me");enterVisual();await refresh()}catch(err){$("#login-error").textContent=err.message}finally{btn.disabled=false}});
  $("#toggle-password").onclick=()=>{const p=$("#login-password");p.type=p.type==="password"?"text":"password";$("#toggle-password").textContent=p.type==="password"?"Mostrar":"Ocultar"};
  $("#menu-toggle").onclick=showMenu;
  $("#close-menu").onclick=hideMenu;
  $("#sidebar-overlay").onclick=hideMenu;
  document.addEventListener("keydown",e=>{
    if(e.key==="Escape"&&$("#sidebar").classList.contains("open")){hideMenu();return}
    trapMobileMenuFocus(e);
  });
  window.addEventListener("resize",()=>{if(window.innerWidth>850&&$("#sidebar").classList.contains("open"))hideMenu();else syncMenuTrigger()});
  syncMenuTrigger();
  $("#refresh").onclick=()=>refresh().then(()=>showToast("Dados atualizados.")).catch(e=>showToast(e.message,true));$("#profile-button").onclick=()=>go("settings");
  $("#main-nav").onclick=e=>{const b=e.target.closest("[data-page]");if(b)go(b.dataset.page)};
  $$(".dialog-close").forEach(x=>x.onclick=()=>$("#editor-dialog").close());$("#editor-form").addEventListener("submit",saveEditor);
  $("#page-content").addEventListener("change",e=>{
    const filter=e.target.closest("[data-filter]");if(filter){filters[filter.dataset.filter]=filter.value;updateFiltered()}
    if(e.target.id==="excel-upload")excelFile=e.target.files?.[0]||null;
    if(e.target.id==="institutional-logo-upload"){
      const file=e.target.files?.[0];
      releaseInstitutionalPreview();
      if(file && file.size>5*1024*1024){e.target.value="";showToast("A assinatura deve ter até 5 MB.",true);return}
      if(file && !["image/png","image/jpeg","image/webp"].includes(file.type)){e.target.value="";showToast("Use PNG, JPG ou WebP.",true);return}
      if(file){
        institutionalPreviewUrl=URL.createObjectURL(file);
        const preview=$(".institutional-preview img");
        if(preview){preview.src=institutionalPreviewUrl;preview.hidden=false;const fallback=$(".institutional-preview [data-institutional-fallback]");if(fallback)fallback.hidden=true}
      }else applyInstitutionalBrand();
    }
  });
  $("#page-content").addEventListener("input",e=>{if(e.target.dataset.filter==="search"){filters.search=e.target.value;updateFiltered()}});
  document.addEventListener("click",async e=>{
    const b=e.target.closest("[data-action]");if(!b)return;
    const action=b.dataset.action,kind=b.dataset.kind,id=b.dataset.id;
    try{
      if(action==="new")editor(page);else if(action==="new-movement")editor("movements");
      else if(action==="edit")editor(kind,id);
      else if(action==="delete"){if(confirm("Excluir este registro permanentemente?")){await api("/api/rows/"+kind+"/"+id,{method:"DELETE"});await refresh();showToast("Registro excluído.")}}
      else if(action==="clear-filters"){filters={};render()}
      else if(action==="export")await doExport();
      else if(action==="preview-import"||action==="commit-import")await importAction(action);
      else if(action==="logout"){await api("/api/logout",{method:"POST"});logoutVisual()}
      else if(action==="upload-avatar"){const file=$("#avatar-upload")?.files?.[0];if(!file)throw Error("Selecione uma foto.");const f=new FormData();f.append("file",file);await api("/api/profile/avatar",{method:"POST",body:f});me=await api("/api/me");enterVisual();showToast("Foto atualizada.")}
      else if(action==="delete-avatar"){await api("/api/profile/avatar",{method:"DELETE"});me=await api("/api/me");enterVisual();showToast("Foto removida.")}
      else if(action==="upload-institutional-logo"){
        const file=$("#institutional-logo-upload")?.files?.[0];
        if(!file)throw Error("Selecione uma logo institucional.");
        if(file.size>5*1024*1024)throw Error("A assinatura precisa ter até 5 MB.");
        const form=new FormData();form.append("file",file);
        await api("/api/branding/institutional",{method:"POST",body:form});
        releaseInstitutionalPreview();
        await loadInstitutionalBrand();
        const input=$("#institutional-logo-upload");if(input)input.value="";
        showToast("Logo institucional aplicada ao login e ao rodapé.");
      }
      else if(action==="delete-institutional-logo"){
        if(!confirm("Restaurar assinatura textual padrão Nexon Labs nas duas telas?"))return;
        await api("/api/branding/institutional",{method:"DELETE"});
        releaseInstitutionalPreview();
        await loadInstitutionalBrand();
        const input=$("#institutional-logo-upload");if(input)input.value="";
        showToast("Assinatura institucional restaurada.");
      }
    }catch(err){showToast(err.message,true)}
  });
  $("#page-content").addEventListener("submit",async e=>{
    if(!["goal-form","profile-form","new-user-form"].includes(e.target.id))return;
    e.preventDefault();const form=e.target,values=Object.fromEntries(new FormData(form));
    try{
      if(form.id==="goal-form"){Object.keys(values).forEach(k=>values[k]=Number(values[k]));await api("/api/settings",{method:"POST",body:JSON.stringify(values)})}
      if(form.id==="profile-form"){await api("/api/profile",{method:"POST",body:JSON.stringify(values)});me=await api("/api/me");enterVisual()}
      if(form.id==="new-user-form"){values.share_ack=$("#share-ack").checked;await api("/api/users",{method:"POST",body:JSON.stringify(values)});form.reset()}
      await refresh();if(form.id==="new-user-form")await loadUsers();showToast("Alterações salvas.");
    }catch(err){showToast(err.message,true)}
  });
}
document.addEventListener("DOMContentLoaded",()=>{bind();loadInstitutionalBrand().catch(()=>applyInstitutionalBrand());start()});
