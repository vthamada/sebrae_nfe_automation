/* Same immutable integer protocol as src/rpa_plan.py. No browser access here. */
(() => {
  "use strict";
  const fail = message => { throw new Error(message); };
  const norm = value => String(value ?? "").trim().replace(/\s+/gu, " ").toUpperCase();
  const canonical = value => {
    if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
    if (value !== null && typeof value === "object") {
      return `{${Object.keys(value).sort().map(k => `${JSON.stringify(k)}:${canonical(value[k])}`).join(",")}}`;
    }
    return JSON.stringify(value);
  };
  async function digest(value) {
    const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(canonical(value)));
    return Array.from(new Uint8Array(bytes), b => b.toString(16).padStart(2, "0")).join("");
  }
  function documentValid(s) {
    if (typeof s !== "string" || !/^(\d{11}|\d{14})$/.test(s) || /^(\d)\1+$/.test(s)) return false;
    const a = [...s].map(Number);
    if (a.length === 11) {
      const d = n => ((a.slice(0, n).reduce((t, v, i) => t + v * (n + 1 - i), 0) * 10) % 11) % 10;
      return d(9) === a[9] && d(10) === a[10];
    }
    const d = w => { const r = w.reduce((t, v, i) => t + a[i] * v, 0) % 11; return r < 2 ? 0 : 11 - r; };
    return d([5,4,3,2,9,8,7,6,5,4,3,2]) === a[12] && d([6,5,4,3,2,9,8,7,6,5,4,3,2]) === a[13];
  }
  function keys(o, expected) {
    if (!o || Array.isArray(o) || typeof o !== "object" || Object.keys(o).sort().join("|") !== expected.split(" ").sort().join("|")) fail("Estrutura do plano inválida.");
  }
  function integer(n, min = 0) {
    if (!Number.isSafeInteger(n) || n < min) fail("Valor inteiro fora do intervalo.");
  }
  function text(s) {
    if (typeof s !== "string" || !s || [...s].length > 200 || norm(s) !== s) fail("Texto não normalizado.");
  }
  const presences = ["0 - Não se aplica", "1 - Operação presencial", "2 - Operação não presencial, pela Internet", "3 - Operação não presencial, Teleatendimento", "5 - Operação presencial, fora do estabelecimento", "9 - Operação não presencial, outros"];
  async function validate(p) {
    keys(p, "schema_version reference issuer_document portal_origin customer issue_date delivery_date operation cfop presence payment freight_mode freight_cents items total_cents notes mode request_hash");
    if (p.schema_version !== 1 || p.mode !== "DRAFT_ONLY") fail("Somente plano DRAFT_ONLY versão 1.");
    text(p.reference); keys(p.customer, "document name"); text(p.customer.name);
    if (!documentValid(p.issuer_document) || p.issuer_document.length !== 14 || !documentValid(p.customer.document)) fail("CPF/CNPJ inválido.");
    if (p.portal_origin !== `https://${p.issuer_document}.emissornfe.sebrae.com.br`) fail("Host do emitente divergente.");
    for (const d of [p.issue_date, p.delivery_date]) {
      if (typeof d !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(d) || !Number.isFinite(Date.parse(d)) || new Date(d).toISOString().slice(0,10) !== d) fail("Data inválida.");
    }
    if (p.operation !== "Venda Dentro do Estado" || p.cfop !== "5102" || p.payment !== "PIX" || p.freight_mode !== "Sem Ocorrência de Transporte" || p.freight_cents !== 0 || !presences.includes(p.presence)) fail("Operação não suportada pela V1.");
    if (typeof p.notes !== "string" || [...p.notes].length > 1500 || p.notes.trim() !== p.notes) fail("Observação inválida.");
    if (!Array.isArray(p.items) || !p.items.length || p.items.length > 100) fail("Itens ausentes ou excessivos.");
    const codes = new Set(); let total = 0n;
    for (const i of p.items) {
      keys(i, "portal_code description unit quantity_milli unit_price_cents discount_cents total_cents");
      if (typeof i.portal_code !== "string" || !/^[A-Za-z0-9._/-]{1,40}$/.test(i.portal_code) || codes.has(i.portal_code)) fail("Código de produto inválido/repetido.");
      codes.add(i.portal_code); text(i.description); text(i.unit);
      integer(i.quantity_milli, 1); integer(i.unit_price_cents); integer(i.discount_cents); integer(i.total_cents);
      if (i.discount_cents !== 0 || i.unit_price_cents < 1 || i.unit_price_cents >= 999999900) fail("V1 exige preço positivo e nenhum desconto de item.");
      if (i.quantity_milli > 999999999999 || i.unit_price_cents > 99999999999999) fail("Valor acima do limite do protocolo.");
      const gross = (BigInt(i.quantity_milli) * BigInt(i.unit_price_cents) + 500n) / 1000n;
      if (gross - BigInt(i.discount_cents) !== BigInt(i.total_cents)) fail("Total do item divergente.");
      total += BigInt(i.total_cents);
    }
    integer(p.total_cents, 1);
    if (p.total_cents > 99999999999999) fail("Total acima do limite do protocolo Python.");
    if (total !== BigInt(p.total_cents)) fail("Total do pedido divergente.");
    const {request_hash, ...body} = p;
    if (!/^[a-f0-9]{64}$/.test(request_hash) || await digest(body) !== request_hash) fail("Arquivo alterado/checksum inválido. Gere novamente pelo Python.");
    return p;
  }
  function portal(url, p) {
    const u = new URL(url);
    if (u.origin !== p.portal_origin || u.pathname !== "/index-sebrae.html" || u.search || u.username || u.password) fail("Aba não pertence ao portal do emitente.");
    return u;
  }
  const money = cents => `${Math.floor(cents / 100)},${String(cents % 100).padStart(2, "0")}`;
  const quantity = milli => `${Math.floor(milli / 1000)}.${String(milli % 1000).padStart(3, "0")}`;
  function cents(s) {
    const v = String(s).replace(/R\$/g, "").replace(/\s/g, "").trim();
    if (!/^(\d+|\d{1,3}(?:\.\d{3})+),\d{2}$/.test(v)) fail("Valor monetário inesperado no portal.");
    const n = Number(v.replace(/\./g, "").replace(",", "")); integer(n); return n;
  }
  const api = {validate, canonical, digest, norm, portal, money, quantity, cents, documentValid};
  globalThis.SebraeRpaProtocol = api;
  if (typeof module !== "undefined") module.exports = api;
})();
