/* AXORA — Estúdio do padrão visual.
   Editor somente para administrador, leitura pública para logo do login e favicon.
   Nunca mistura identidade visual e registros financeiros. */
"use strict";
const brandKitSlots={
  primary:{label:"Logo principal",detail:"Marca horizontal para login e peças institucionais",width:1400,height:420},
  secondary:{label:"Logo secundária",detail:"Marca compacta para o menu lateral",width:1100,height:340},
  icon:{label:"Ícone do aplicativo",detail:"Versão quadrada para atalhos e aplicativos",width:1024,height:1024},
  favicon:{label:"Favicon",detail:"Versão quadrada para abas e navegadores",width:256,height:256}
};
let brandKit={};

function brandKitPanel(){
  const cards=Object.entries(brandKitSlots).map(([slot,item])=>
    '<div class="brand-kit-card">'+
      '<div class="brand-kit-preview"><img data-kit-preview="'+slot+'" alt="Prévia: '+esc(item.label)+'" hidden><img class="brand-kit-placeholder" src="/assets/axora-mark.svg" alt="Marca padrão AXORA"></div>'+
      '<div class="brand-kit-card-content"><div class="brand-kit-card-title">'+esc(item.label)+'<span class="brand-kit-dimensions">'+item.width+' × '+item.height+' px</span></div>'+
      '<p>'+esc(item.detail)+'</p><small data-kit-state="'+slot+'">Padrão AXORA ativo</small>'+
      (me?.is_admin?'<div class="field"><label for="brand-kit-file-'+slot+'">Imagem PNG, JPG ou WebP (até 5 MB)</label><input id="brand-kit-file-'+slot+'" type="file" accept="image/png,image/jpeg,image/webp"></div><div class="brand-kit-actions"><button class="btn primary small" type="button" data-action="save-brand-kit" data-slot="'+slot+'">Aplicar</button><button class="btn ghost small" type="button" data-action="export-brand-kit" data-slot="'+slot+'">Baixar PNG</button><button class="btn ghost small" type="button" data-action="reset-brand-kit" data-slot="'+slot+'">Restaurar</button></div>':
      '<div class="notice">Apenas administradores podem alterar o padrão visual.</div>')+
    '</div></div>'
  ).join("");
  return '<div class="brand-kit-intro"><p>Configure a identidade AXORA com quatro versões independentes. O PNG exportado mantém o fundo transparente, a proporção da arte e o tamanho oficial de cada aplicação.</p><p>Para o login e o menu escuros, use preferencialmente versões com letras claras. A assinatura institucional Nexon Labs continua em seu painel separado.</p></div><div class="brand-kit-grid">'+cards+'</div>';
}
function kitImageUrl(slot,item){
  return "/api/brand-kit/"+slot+"/image?v="+encodeURIComponent(item?.updated_at||"");
}
function swapKitImage(image,container,item,slot){
  if(!image||!container)return;
  if(!item?.configured){
    image.hidden=true;
    image.onload=null;image.onerror=null;
    image.removeAttribute("src");
    container.classList.remove("brand-custom");
    return;
  }
  const src=kitImageUrl(slot,item);
  if(image.getAttribute("src")===src)return;
  image.onload=()=>{
    if(image.getAttribute("src")!==src)return;
    image.hidden=false;
    container.classList.add("brand-custom");
  };
  image.onerror=()=>{
    image.hidden=true;
    container.classList.remove("brand-custom");
  };
  image.src=src;
}
function applyBrandKit(){
  for(const [slot] of Object.entries(brandKitSlots)){
    const item=brandKit[slot],available=Boolean(item?.configured);
    const url=kitImageUrl(slot,item);
    document.querySelectorAll('[data-kit-preview="'+slot+'"]').forEach(image=>{
      image.hidden=!available;
      if(available&&image.getAttribute("src")!==url)image.setAttribute("src",url);
      if(!available)image.removeAttribute("src");
      const placeholder=image.parentElement?.querySelector(".brand-kit-placeholder");
      if(placeholder)placeholder.hidden=available;
    });
    const status=document.querySelector('[data-kit-state="'+slot+'"]');
    if(status)status.textContent=available?"Personalizada e ativa":"Padrão AXORA ativo";
  }
  const login=$("#axora-login-logo"),sidebar=$("#axora-sidebar-logo");
  swapKitImage(login,login?.parentElement,brandKit.primary,"primary");
  swapKitImage(sidebar,sidebar?.parentElement,brandKit.secondary,"secondary");
  const favicon=$("#axora-favicon"),apple=$('link[rel="apple-touch-icon"]');
  const icon=brandKit.favicon?.configured?"favicon":brandKit.icon?.configured?"icon":null;
  const href=icon?kitImageUrl(icon,brandKit[icon]):"/assets/axora-mark.svg";
  if(favicon&&favicon.getAttribute("href")!==href){
    favicon.href=href;favicon.type=icon?"image/webp":"image/svg+xml";
  }
  if(apple&&apple.getAttribute("href")!==href)apple.href=href;
}
async function loadBrandKit(){
  brandKit=await api("/api/brand-kit");
  applyBrandKit();
}
async function exportBrandKitPNG(slot){
  const preset=brandKitSlots[slot],item=brandKit[slot];
  if(!preset||!item?.configured)throw Error("Envie uma imagem para gerar este modelo.");
  const img=new Image(),src=kitImageUrl(slot,item);
  // Decodificação direta no navegador: não enviar a imagem para outros serviços.
  await new Promise((resolve,reject)=>{
    img.onload=resolve;img.onerror=()=>reject(Error("Falha ao carregar a imagem."));
    img.src=src;
    if(img.complete&&img.naturalWidth)resolve();
  });
  const canvas=document.createElement("canvas");
  canvas.width=preset.width;canvas.height=preset.height;
  const ctx=canvas.getContext("2d");
  if(!ctx)throw Error("Seu navegador não permite gerar este PNG.");
  const scale=Math.min((preset.width*.90)/img.naturalWidth,(preset.height*.90)/img.naturalHeight);
  const w=img.naturalWidth*scale,h=img.naturalHeight*scale;
  ctx.clearRect(0,0,preset.width,preset.height);
  ctx.drawImage(img,(preset.width-w)/2,(preset.height-h)/2,w,h);
  const blob=await new Promise(resolve=>canvas.toBlob(resolve,"image/png"));
  if(!blob)throw Error("Falha ao exportar o arquivo.");
  const url=URL.createObjectURL(blob),a=document.createElement("a");
  a.href=url;a.download="AXORA_"+slot+"_"+preset.width+"x"+preset.height+".png";
  document.body.append(a);a.click();a.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1500);
}
async function brandKitClick(event){
  const button=event.target.closest('[data-action="save-brand-kit"],[data-action="reset-brand-kit"],[data-action="export-brand-kit"]');
  if(!button)return;
  const slot=button.dataset.slot;
  if(!brandKitSlots[slot])return;
  if(!me?.is_admin){showToast("Permissão de administrador necessária.",true);return}
  if(button.disabled)return;
  button.disabled=true;
  try{
    if(button.dataset.action==="save-brand-kit"){
      const input=$("#brand-kit-file-"+slot),file=input?.files?.[0];
      if(!file)throw Error("Selecione a imagem para "+brandKitSlots[slot].label+".");
      if(file.size>5*1024*1024)throw Error("O arquivo deve ter até 5 MB.");
      if(!["image/png","image/jpeg","image/webp"].includes(file.type))throw Error("Envie PNG, JPG ou WebP.");
      const form=new FormData();form.append("file",file);
      await api("/api/brand-kit/"+slot,{method:"POST",body:form});
      input.value="";
      await loadBrandKit();
      showToast("Logo aplicada: "+brandKitSlots[slot].label+".");
    }else if(button.dataset.action==="reset-brand-kit"){
      if(!confirm("Restaurar a logo AXORA padrão deste espaço?"))return;
      await api("/api/brand-kit/"+slot,{method:"DELETE"});
      await loadBrandKit();
      const input=$("#brand-kit-file-"+slot);if(input)input.value="";
      showToast("Versão padrão restaurada.");
    }else{
      await exportBrandKitPNG(slot);
      showToast("PNG com tamanho padrão gerado.");
    }
  }catch(error){showToast(error.message||"Não foi possível atualizar a logo.",true)}
  finally{button.disabled=false}
}
document.addEventListener("DOMContentLoaded",()=>{
  document.addEventListener("click",brandKitClick);
  loadBrandKit().catch(()=>applyBrandKit());
});
