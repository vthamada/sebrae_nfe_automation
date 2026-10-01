/* UI-only runner in the isolated content-script world. Never calls portal APIs. */
(() => {
  "use strict";
  const P = globalThis.SebraeRpaProtocol;
  const fail = message => { throw new Error(message); };
  const visible = e => !!e && !!e.getClientRects().length && !e.closest('[aria-hidden="true"],.ng-hide,[hidden]');
  const all = (selector, root = document) => [...root.querySelectorAll(selector)].filter(visible);
  function one(selector, root = document) {
    const es = all(selector, root);
    if (es.length !== 1) fail(`Campo ausente/ambíguo: ${selector}. Interrompido sem adivinhar seletores.`);
    return es[0];
  }
  const model = (name, root = document) => one(`[ng-model="${name}"]`, root);
  const selected = e => P.norm(e.selectedOptions?.[0]?.textContent || "");
  const editable = e => { if (!visible(e) || e.disabled || e.readOnly) fail("Campo bloqueado; confira situação/autenticação da nota."); };
  function set(e, value) {
    editable(e); e.focus();
    if (e.maxLength >= 0 && String(value).length > e.maxLength) fail("Texto excede o limite do campo do portal.");
    const proto = e.tagName === "SELECT" ? HTMLSelectElement.prototype : e.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(e, String(value));
    e.dispatchEvent(new Event("input", {bubbles:true}));
    e.dispatchEvent(new Event("change", {bubbles:true}));
    e.blur();
  }
  function select(e, label) {
    if (selected(e) === P.norm(label)) return;
    const options = [...e.options].filter(o => P.norm(o.textContent) === P.norm(label));
    if (options.length !== 1) fail(`Opção ausente/ambígua: ${label}.`);
    set(e, options[0].value);
    if (selected(e) !== P.norm(label)) fail(`Seleção não confirmada: ${label}.`);
  }
  function click(e) {
    editable(e);
    // Small allowlist: no Emitir, Enviar, Cancelar, certificate or account actions.
    const allowed = e.matches('.bt-add-item,.bt-discount,.bt-select-payment,[role="option"],label[for="submitItemDiscountForm"]') ||
      e.matches('button[title="Salvar"]') || (e.closest('[role="option"]')) ||
      (P.norm(e.textContent) === "OK" && e.closest('.modal,.modal-dialog,.bootbox'));
    if (!allowed) fail("Ação fora da lista de rascunho.");
    e.click();
  }
  function wait(predicate, description, timeout = 20000) {
    return new Promise((resolve, reject) => {
      const start = Date.now(); let observer, timer;
      const done = () => { observer?.disconnect(); clearInterval(timer); };
      const check = () => {
        try {
          const result = predicate();
          if (result) { done(); resolve(result); }
          else if (Date.now() - start >= timeout) { done(); reject(new Error(`Tempo excedido: ${description}. Confira a aba; não repita gravações em dúvida.`)); }
        } catch (error) { done(); reject(error); }
      };
      observer = new MutationObserver(check); observer.observe(document.documentElement, {childList:true, subtree:true, attributes:true, characterData:true});
      // Form values may change without DOM mutation. This is predicate polling, not a blind delay.
      timer = setInterval(check, 75); check();
    });
  }
  function quantity(s) {
    const text = String(s).trim().replace(/\s/g, "");
    if (!/^\d+(?:[,.]\d{1,3})?$/.test(text)) fail("Quantidade inesperada no portal.");
    const [whole, fraction = ""] = text.replace(",", ".").split(".");
    const n = BigInt(whole) * 1000n + BigInt(fraction.padEnd(3, "0"));
    if (n > BigInt(Number.MAX_SAFE_INTEGER)) fail("Quantidade excessiva."); return Number(n);
  }
  function rowData(row) {
    const q = one(".quantity", row); const b = one("b", q);
    const copy = q.cloneNode(true); copy.querySelectorAll('b,.unit-edit-ico').forEach(e => e.remove());
    const prices = all("td.price", row);
    if (prices.length !== 2) fail("Colunas de preço não correspondem ao mapa.");
    const price = e => { const copy = e.cloneNode(true); copy.querySelectorAll(".from").forEach(s => s.remove()); return P.cents(copy.textContent); };
    return {portal_code:one(".barcode",row).textContent.trim(), description:P.norm(one(".name",row).textContent),
      unit:P.norm(copy.textContent), quantity_milli:quantity(b.textContent), unit_price_cents:price(prices[0]), total_cents:price(prices[1])};
  }
  const rows = () => all("tr").filter(r => r.querySelector(".barcode"));
  function itemMatches(row, item) {
    const r = rowData(row);
    return ["portal_code","description","unit","quantity_milli","unit_price_cents","total_cents"].every(k => r[k] === item[k]);
  }
  function paymentRows() {
    return all(".payment-summary tbody tr").filter(r => !r.querySelector(".no-informed-payment") && all("td", r).length >= 2 && P.norm(all("td", r)[0].textContent));
  }
  function total() { return P.cents(one(".total-value.equal .value").textContent); }
  function assert(condition, text) { if (!condition) fail(text); }
  function draftPage(plan, fresh) {
    const url = P.portal(location.href, plan);
    assert(fresh ? url.hash === "#/invoice/new" : /^#\/invoice\/detail\/\d+$/.test(url.hash), "Abra uma NOVA NF-e vazia. O assistente não altera notas existentes.");
    assert(!document.body.innerText.includes("NF-e emitida com sucesso"), "Nota já emitida: operação bloqueada.");
    one('select[ng-model="controller.currentInvoice.InvoiceModel"]');
  }
  function empty(plan) {
    draftPage(plan, true);
    assert(rows().length === 0 && paymentRows().length === 0, "Formulário já contém itens ou pagamentos. Não será sobrescrito.");
    const clients = all('input[placeholder="Nome do cliente ou fornecedor"]');
    assert(!clients.some(e=>e.value.trim()), "Formulário já contém cliente. Não será sobrescrito.");
    const general = document.querySelector("#formGeneralInfo");
    assert(general && !general.querySelector('.ng-dirty'), "Formulário já foi editado. Abra outra NF-e vazia.");
  }
  function verify(plan, saved = false) {
    draftPage(plan, !saved);
    assert(selected(model("controller.currentInvoice.InvoiceModel")) === "NF-E", "Tipo de nota divergente.");
    assert(selected(model("controller.currentInvoice.OperationTypeID")) === "SAÍDA", "Tipo de operação divergente.");
    for (const name of ["IsExterior","IsComplementary","IsAdjust","UseInputOutputHour"]) {
      assert(!all(`[ng-model="controller.currentInvoice.${name}"]`).some(e=>e.checked),"Exportação, complemento, ajuste ou hora de entrega não suportados pela V1.");
    }
    for (const [m, value] of [["IssueDate",plan.issue_date],["InputOutputDate",plan.delivery_date]]) assert(model(`controller.currentInvoice.${m}`).value === value, `Data ${m} divergente.`);
    const documentField = model(`controller.currentInvoice.PersonInvoice.${plan.customer.document.length === 14 ? "Cnpj" : "Cpf"}`);
    assert(documentField.value.replace(/\D/g, "") === plan.customer.document, "Documento do destinatário divergente.");
    assert(P.norm(model("controller.currentInvoice.PersonInvoice.OfficialName").value) === plan.customer.name, "Nome do destinatário divergente.");
    assert(selected(model("controller.currentInvoice.TransactionNatureID")) === P.norm(plan.operation), "Natureza divergente.");
    assert(/^\[5102\]/.test(one('input[name="DefaultCfop"]').value), "CFOP padrão divergente.");
    const actual = rows(); assert(actual.length === plan.items.length, "Número de itens divergente.");
    for (const i of plan.items) {
      const matching = actual.filter(r=>one(".barcode",r).textContent.trim()===i.portal_code);
      assert(matching.length===1 && itemMatches(matching[0],i), `Item/quantidade/preço divergente: ${i.portal_code}.`);
    }
    assert(total() === plan.total_cents, "Total da nota divergente.");
    for (const m of ["controller.invoiceDiscount","controller.currentInvoice.Shipping","controller.currentInvoice.GeneralTaxes","controller.currentInvoice.Insurance"]) assert(P.cents(model(m).value) === 0, "Desconto global ou despesas não previstas.");
    assert(selected(model("controller.shippingTypeID")) === P.norm(plan.freight_mode), "Modalidade de transporte divergente.");
    const payments = paymentRows(); assert(payments.length === 1, "Pagamentos ausentes ou duplicados.");
    const cells = all("td",payments[0]); assert(P.norm(cells[0].textContent)==="PIX" && P.cents(cells[1].textContent)===plan.total_cents,"Pagamento divergente.");
    return {status:"CHECKED",total_cents:total(),item_count:actual.length,issued:false};
  }
  async function typeahead(input, query, matches) {
    set(input,query);
    const option = await wait(() => {
      const id = input.getAttribute("aria-owns"); const box = id && document.getElementById(id);
      if (!visible(box) || input.classList.contains("loader")) return false;
      const options = all('[role="option"]',box).filter(e=>matches(P.norm(e.textContent)));
      if (options.length > 1) fail("Busca ambígua. Use código/documento e nome exatos.");
      return options[0];
    },"resultado exato da busca");
    click(option.querySelector("a") || option);
    await wait(()=>input.getAttribute("aria-expanded")==="false" && !input.classList.contains("loader"),"fechamento da busca");
  }
  async function fill(plan) {
    empty(plan);
    select(model("controller.currentInvoice.InvoiceModel"),"NF-e");
    await wait(()=>all('[ng-model="controller.currentInvoice.OperationTypeID"]').length,"tipo entrada/saída");
    select(model("controller.currentInvoice.OperationTypeID"),"Saída");
    set(model("controller.currentInvoice.IssueDate"),plan.issue_date);
    set(model("controller.currentInvoice.InputOutputDate"),plan.delivery_date);
    const client = await wait(()=>all('input[placeholder="Nome do cliente ou fornecedor"]')[0],"busca do cliente");
    await typeahead(client,plan.customer.name,text => {
      const m = text.match(/^CLIENTE:\s*\[([^\]]+)\]\s*(.+)$/);
      return m && m[1].replace(/\D/g,"")===plan.customer.document && P.norm(m[2])===plan.customer.name;
    });
    await wait(()=>all('[ng-model="controller.currentInvoice.TransactionNatureID"]').length,"natureza de operação");
    select(model("controller.currentInvoice.TransactionNatureID"),plan.operation);
    await typeahead(one('input[name="DefaultCfop"]'),"5102", text=>text.startsWith("[5102] "));
    select(model("controller.shippingTypeID"),plan.freight_mode);
    for (const item of plan.items) {
      const input = one('input[placeholder="DIGITE O NOME OU CÓDIGO DO ITEM"]');
      await typeahead(input,item.portal_code,text=>text===P.norm(`Produto: ${item.portal_code} - ${item.description}`));
      // setItem loads asynchronously and resets Amount to 1. Wait for completed data first.
      await wait(()=> selected(model("controller.newItem.ItemUnit"))===item.unit && quantity(model("controller.newItem.Amount").value||"0")===1000 &&
        !input.classList.contains("loader") && P.cents(one('[name="newItemForm"] .item-price .form-group:last-child .price').textContent)>0,"produto totalmente carregado");
      assert(!all('[ng-model="controller.currentSize"],[ng-model="controller.currentColor"]').length,"Produto com grade não suportado.");
      set(model("controller.newItem.Amount"),P.quantity(item.quantity_milli).replace(".",","));
      await wait(()=>quantity(model("controller.newItem.Amount").value)===item.quantity_milli,"quantidade aplicada");
      const count = rows().length; click(one(".bt-add-item"));
      const row = await wait(()=>{
        if (rows().length!==count+1) return false;
        return rows().find(r=>one(".barcode",r).textContent.trim()===item.portal_code);
      },"inclusão do item");
      assert(rowData(row).description===item.description && rowData(row).unit===item.unit,"Produto selecionado não corresponde ao plano.");
      // Edit only this invoice's line; never change catalog sale price or classification.
      click(one(".bt-discount",row));
      const modal = await wait(()=>all('[name="itemDiscountForm"]')[0],"editor do item");
      const ncm = model("controller.currentItem.Item.Ncm",modal).value;
      assert(/\[\d{8}\]/.test(ncm),"NCM ausente no cadastro. Não será inventado.");
      assert(/^\[5102\]/.test(model("controller.currentInvoiceItemCfop",modal).value),"CFOP do item divergente. Não será corrigido por suposição.");
      set(model("controller.currentItem.Amount",modal),P.quantity(item.quantity_milli).replace(".",","));
      assert(selected(model("controller.currentItem.ItemUnit",modal))===item.unit,"Unidade do editor divergente.");
      set(model("controller.currentItem.Value",modal),P.money(item.unit_price_cents));
      set(model("controller.currentItem.Discount",modal),P.money(item.discount_cents));
      // CFOP stays inherited from explicit header. No automatic fiscal classification.
      click(one('label[for="submitItemDiscountForm"]'));
      await wait(()=>!visible(modal),"fechamento do editor");
      const updated = rows().filter(r=>one(".barcode",r).textContent.trim()===item.portal_code);
      assert(updated.length===1 && itemMatches(updated[0],item),`Conferência do item falhou: ${item.portal_code}.`);
    }
    select(model("controller.newPaymentType"),"PIX");
    const conditions = await wait(()=>{
      const e=model("controller.currentPaymentCondition"); const options=[...e.options].filter(o=>o.value!=="?" && o.value!=="");
      return options.length ? {e,options} : false;
    },"condição Pix");
    assert(conditions.options.length===1,"Pix possui várias condições; V1 requer conferência manual.");
    select(conditions.e,conditions.options[0].textContent);
    set(model("controller.newPaymentTypeValue"),P.money(plan.total_cents)); click(one(".bt-select-payment"));
    await wait(()=>paymentRows().length===1,"inclusão do Pix");
    return verify(plan);
  }
  async function save() {
    const button = one('button[title="Salvar"]'); click(button);
    const success = await wait(()=>all('.modal,.bootbox').find(e=>e.textContent.includes("Nota salva com sucesso!")),"confirmação de salvamento",30000);
    const ok = all("button",success).filter(e=>P.norm(e.textContent)==="OK");
    assert(ok.length===1,"Confirmação de salvamento ambígua."); click(ok[0]);
    await wait(()=>/^#\/invoice\/detail\/\d+$/.test(location.hash),"identificador do rascunho salvo");
    const id=location.hash.split("/").pop();
    assert(/^\d+$/.test(id) && Number(id)>0,"Identificador de rascunho inválido.");
    return {portal_id:id,portal_url:location.href,issued:false};
  }
  async function execute(operation, plan) {
    try {
      await P.validate(plan);
      if (operation === "CHECK" || operation === "CHECK_EMPTY") { empty(plan); return {status:"EMPTY_FORM_CONFIRMED",issued:false}; }
      if (operation === "CHECK_FILLED") return verify(plan);
      if (operation === "FILL") return await fill(plan);
      if (operation === "SAVE_BASE") { verify(plan); return await save(); }
      if (operation === "FINALIZE") {
        verify(plan,true);
        const id=location.hash;
        select(one("#selConsumerPresenceCode"),plan.presence);
        const notes = `${plan.notes}${plan.notes ? "\n" : ""}RPA:${plan.reference}`;
        set(one("#txtAdditionalInformation"),notes);
        await save(); assert(location.hash===id,"Identificador mudou durante revisão.");
        verify(plan,true);
        assert(selected(one("#selConsumerPresenceCode"))===P.norm(plan.presence) && one("#txtAdditionalInformation").value===notes,"Presença/observação não confirmadas.");
        return {status:"SAVED_DRAFT",issued:false};
      }
      if (operation === "RECHECK") {
        await wait(()=>all('[ng-model="controller.currentInvoice.PersonInvoice.OfficialName"]').some(e=>P.norm(e.value)===plan.customer.name) && rows().length===plan.items.length,"rascunho recarregado",30000);
        verify(plan,true);
        const notes = `${plan.notes}${plan.notes ? "\n" : ""}RPA:${plan.reference}`;
        assert(selected(one("#selConsumerPresenceCode"))===P.norm(plan.presence) && one("#txtAdditionalInformation").value===notes,"Presença/observação não persistidas.");
        return {status:"SAVED_DRAFT",issued:false,portal_id:location.hash.split("/").pop(),portal_url:location.href};
      }
      fail("Comando fora do fluxo de rascunhos.");
    } catch (error) { return {error:error.message,issued:false}; }
  }
  globalThis.SebraeDraftRpa = {execute};
})();
