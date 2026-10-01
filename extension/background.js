/* Persistent journal before writes; one operation at a time. No cookie/API access. */
"use strict";
importScripts("protocol.js");
const P = SebraeRpaProtocol;
let busy = false;
async function reload(tabId) {
  await new Promise((resolve, reject) => {
    const finish = error => { clearTimeout(timer); chrome.tabs.onUpdated.removeListener(listener); error ? reject(error) : resolve(); };
    const listener = (id, info) => { if (id === tabId && info.status === "complete") finish(); };
    const timer = setTimeout(()=>finish(new Error("Não foi possível recarregar o rascunho para conferir persistência.")),30000);
    chrome.tabs.onUpdated.addListener(listener);
    chrome.tabs.reload(tabId).catch(finish);
  });
}
chrome.action.onClicked.addListener(async tab => {
  const supported = /^https:\/\/\d{14}\.emissornfe\.sebrae\.com\.br\/index-sebrae\.html(?:#.*)?$/.test(tab.url || "");
  await chrome.tabs.create({url: chrome.runtime.getURL(`panel.html?target=${tab.id}${supported ? "" : "&unsupported=1"}`)});
});
async function run(tabId, operation, plan) {
  const tab = await chrome.tabs.get(tabId); P.portal(tab.url, plan);
  await chrome.scripting.executeScript({target: {tabId}, files: ["protocol.js", "runner.js"]});
  const results = await chrome.scripting.executeScript({target: {tabId}, func: (op, p) => globalThis.SebraeDraftRpa.execute(op, p), args: [operation, plan]});
  if (results.length !== 1 || !results[0].result) throw new Error("O formulário não retornou confirmação; confira a aba antes de repetir.");
  if (results[0].result.error) throw new Error(results[0].result.error);
  return results[0].result;
}
async function handle(message) {
  if (busy) throw new Error("Outro comando está em execução; aguarde.");
  busy = true;
  let key, entry;
  try {
    const {action, plan, tabId} = message;
    if (!Number.isInteger(tabId) || !["CHECK", "FILL", "SAVE", "RECEIPT"].includes(action)) throw new Error("Comando inválido.");
    await P.validate(plan);
    key = `draft:${await P.digest([plan.issuer_document, plan.reference])}`;
    entry = (await chrome.storage.local.get(key))[key];
    if (entry && entry.request_hash !== plan.request_hash) throw new Error("Referência já utilizada com outro conteúdo. Concilie antes de continuar.");
    if (action === "RECEIPT") {
      if (!entry) throw new Error("Não há registro para este pedido.");
      return entry;
    }
    if (action === "CHECK") return await run(tabId, "CHECK", plan);
    if (action === "FILL" && entry) throw new Error(`Pedido já iniciado (${entry.status}). Não será repetido; confira o registro/portal.`);
    if (action === "SAVE" && (!entry || entry.status !== "FILLED" || entry.tab_id !== tabId)) throw new Error("Salvar exige montagem confirmada nesta mesma aba. Não recrie pedidos em dúvida.");
    // A read-only preflight failure does not claim or poison this reference.
    await run(tabId, action === "FILL" ? "CHECK_EMPTY" : "CHECK_FILLED", plan);
    entry = {...entry, schema_version: 1, request_hash: plan.request_hash, tab_id: tabId,
      status: action === "FILL" ? "RUNNING" : "SAVE_STARTED", issued: false,
      total_cents: plan.total_cents, item_count: plan.items.length, updated_at: new Date().toISOString()};
    await chrome.storage.local.set({[key]: entry});
    try {
      if (action === "FILL") {
        await run(tabId, "FILL", plan); entry.status = "FILLED";
      } else {
        const base = await run(tabId, "SAVE_BASE", plan);
        entry = {...entry, ...base, status: "SAVED_REVIEW_PENDING"};
        // Save the identifier before editing the same draft for presence/notes.
        await chrome.storage.local.set({[key]: entry});
        await run(tabId, "FINALIZE", plan);
        await reload(tabId);
        const confirmed = await run(tabId, "RECHECK", plan);
        if (confirmed.portal_id !== entry.portal_id || confirmed.portal_url !== entry.portal_url) throw new Error("O ID/URL mudou durante a conferência. Concilie o rascunho original.");
        entry.status = "SAVED_DRAFT";
      }
      entry.updated_at = new Date().toISOString();
      await chrome.storage.local.set({[key]: entry});
      return entry;
    } catch (error) {
      entry.status = entry.portal_id ? "SAVED_REVIEW_PENDING" : "UNCERTAIN";
      entry.updated_at = new Date().toISOString();
      await chrome.storage.local.set({[key]: entry});
      throw new Error(`${error.message} Registro ${entry.status}. Confira o portal; não repita nem troque a referência para tentar novamente.`);
    }
  } finally { busy = false; }
}
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (sender.id !== chrome.runtime.id || !sender.url?.startsWith(chrome.runtime.getURL("panel.html")) || sender.tab?.url !== sender.url) return false;
  handle(message).then(result => respond({ok: true, result}), error => respond({ok: false, error: error.message}));
  return true;
});
