/* Nexon Labs PWA: instalação sem armazenamento local de informações financeiras. */
(() => {
  if (!("serviceWorker" in navigator) || !window.isSecureContext) return;
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/service-worker.js", {scope: "/"})
      .catch(() => { /* O aplicativo permanece utilizável no navegador. */ });
  }, {once: true});
})();
