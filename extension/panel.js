"use strict";
const P = SebraeRpaProtocol;
const $ = id => document.getElementById(id);
const tabId = Number(new URL(location.href).searchParams.get("target"));
let plan = null, receipt = null, pending = false;
if (new URL(location.href).searchParams.has("unsupported")) {
  $("status").textContent = "Abra a aba do emissor Sebrae da sua empresa (CNPJ.emissornfe.sebrae.com.br/index-sebrae.html) e clique na extensão nessa aba. Não há controle desta página.";
}
function controls() {
  const ready = !!plan && !pending;
  $("file").disabled = pending; $("approval").disabled = pending;
  $("check").disabled = !ready; $("receipt").disabled = !ready;
  $("fill").disabled = !ready || !$("approval").checked || !!receipt;
  $("save").disabled = !ready || !$("approval").checked || receipt?.status !== "FILLED";
  $("export").disabled = pending || !receipt;
}
function text(element, value) { element.textContent = value; }
function preview() {
  $("preview").replaceChildren();
  const line = document.createElement("p");
  text(line, `${plan.reference} — ${plan.customer.name} (${plan.customer.document})\nEmitente: ${plan.issuer_document} — ${plan.portal_origin}\nEmissão: ${plan.issue_date}; entrega: ${plan.delivery_date}; ${plan.presence}; PIX; sem transporte`);
  $("preview").append(line);
  const table = document.createElement("table");
  for (const values of [["Código / produto", "Qtd / unidade", "Unitário", "Desconto", "Total"], ...plan.items.map(i => [
    `${i.portal_code} — ${i.description}`, `${P.quantity(i.quantity_milli)} ${i.unit}`, P.money(i.unit_price_cents), P.money(i.discount_cents), P.money(i.total_cents)])]) {
    const row = table.insertRow(); for (const value of values) text(row.insertCell(), value);
  }
  $("preview").append(table);
  const total = document.createElement("p"); text(total, `Total: R$ ${P.money(plan.total_cents)} — ${plan.items.length} itens. ${plan.notes}`); $("preview").append(total);
}
$("file").addEventListener("change", async () => {
  plan = null; receipt = null; $("approval").checked = false; $("preview").replaceChildren();
  try {
    const file = $("file").files[0]; if (!file || file.size > 200000) throw new Error("Selecione um JSON de até 200 KB.");
    plan = await P.validate(JSON.parse((await file.text()).replace(/^\uFEFF/, "")));
    preview(); text($("status"), "Plano válido. Na aba Sebrae, abra uma NOVA NF-e vazia; depois confira a aba. Nenhuma nota existente será editada.");
  } catch (error) { text($("status"), error.message); }
  controls();
});
$("approval").addEventListener("change", controls);
for (const [id, action] of [["check","CHECK"],["fill","FILL"],["save","SAVE"],["receipt","RECEIPT"]]) {
  $(id).addEventListener("click", async () => {
    pending = true; controls(); text($("status"), "Executando; não mexa na aba Sebrae. Aguarde a confirmação. Não emite notas.");
    try {
      const response = await chrome.runtime.sendMessage({action, plan, tabId});
      if (!response?.ok) throw new Error(response?.error || "Sem resposta. Consulte o registro antes de repetir.");
      if (action !== "CHECK") receipt = response.result;
      text($("status"), JSON.stringify(response.result, null, 2));
    } catch (error) {
      text($("status"), error.message);
      // A disconnected panel is not evidence that no write happened.
      try { const r = await chrome.runtime.sendMessage({action:"RECEIPT", plan, tabId}); if (r?.ok) receipt = r.result; } catch (_) { receipt = {status: "UNKNOWN", issued:false}; }
    } finally { pending = false; controls(); }
  });
}
$("export").addEventListener("click", () => {
  const url = URL.createObjectURL(new Blob([JSON.stringify(receipt, null, 2)], {type:"application/json"}));
  const a = document.createElement("a"); a.href = url; a.download = `resultado-${plan.request_hash.slice(0,12)}.json`; a.click(); URL.revokeObjectURL(url);
});
