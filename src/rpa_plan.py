"""Immutable, exact-value requests for the supervised Chrome draft assistant.

This module never opens a browser, emits an invoice or changes stock.
"""
import hashlib
import json
import re
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from src.validators import (
    format_money, format_quantity, money_to_cents, normalize_document,
    normalize_text, quantity_to_milli, validate_document,
)

PRESENCE = {
    "0": "0 - Não se aplica", "1": "1 - Operação presencial",
    "2": "2 - Operação não presencial, pela Internet",
    "3": "3 - Operação não presencial, Teleatendimento",
    "5": "5 - Operação presencial, fora do estabelecimento",
    "9": "9 - Operação não presencial, outros",
}
MAX_SAFE = 9_007_199_254_740_991


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _text(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} deve ser texto.")
    text = normalize_text(value)
    if not text or len(text) > 200:
        raise ValueError(f"{field} obrigatório, máximo 200 caracteres.")
    return text


def _date(value, field):
    try:
        text = str(value)
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            raise ValueError()
        date.fromisoformat(text)
        return text
    except (ValueError, TypeError):
        raise ValueError(f"{field} deve usar uma data válida AAAA-MM-DD.") from None


def build_plan(order):
    """V1: NF-e saída, revenda dentro do estado, Pix e sem transporte.

    These choices must be explicitly supplied, not inferred from customer data.
    Product codes are the codes shown in the portal search, not assumed GTINs.
    """
    if not isinstance(order, dict):
        raise ValueError("Pedido deve ser um objeto JSON.")
    issuer = normalize_document(order.get("issuer_document"))
    if len(issuer) != 14 or not validate_document(issuer):
        raise ValueError("CNPJ do emitente inválido.")
    customer = order.get("customer", {})
    if not isinstance(customer, dict):
        raise ValueError("Destinatário deve ser um objeto JSON.")
    document = normalize_document(customer.get("document"))
    if not validate_document(document):
        raise ValueError("CPF/CNPJ do destinatário inválido.")
    if order.get("operation") != "Venda Dentro do Estado" or str(order.get("cfop")) != "5102":
        raise ValueError("V1 suporta somente Venda Dentro do Estado / CFOP 5102 revisado.")
    if order.get("payment") != "PIX" or order.get("freight_mode") != "Sem Ocorrência de Transporte":
        raise ValueError("V1 exige PIX e Sem Ocorrência de Transporte explicitamente.")
    if money_to_cents(order.get("freight", "0")) != 0:
        raise ValueError("Frete diferente de zero não suportado na V1.")
    presence = str(order.get("presence", ""))
    if presence not in PRESENCE:
        raise ValueError("Indicador de presença obrigatório: 0, 1, 2, 3, 5 ou 9.")
    raw_items = order.get("items")
    if not isinstance(raw_items, list) or not 1 <= len(raw_items) <= 100:
        raise ValueError("Pedido deve possuir entre 1 e 100 itens.")
    items, codes, total = [], set(), 0
    for item in raw_items:
        if not isinstance(item, dict):
            raise ValueError("Cada item deve ser um objeto JSON.")
        code = str(item.get("portal_code", "")).strip()
        if not re.fullmatch(r"[A-Za-z0-9._/-]{1,40}", code) or code in codes:
            raise ValueError("Código do portal ausente, inválido ou repetido; consolide a quantidade.")
        codes.add(code)
        quantity = quantity_to_milli(item.get("quantity"))
        price = money_to_cents(item.get("unit_price"))
        discount = money_to_cents(item.get("discount", "0"))
        if discount != 0 or not 1 <= price < 999_999_900:
            raise ValueError("V1 exige item sem desconto e preço positivo inferior a R$ 9.999.999,00.")
        gross = int((Decimal(price) * quantity / 1000).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        if discount > gross or max(quantity, price, gross) > MAX_SAFE:
            raise ValueError("Valores do item fora do intervalo permitido.")
        line_total = gross - discount
        total += line_total
        items.append({
            "portal_code": code, "description": _text(item.get("description"), "Descrição"),
            "unit": _text(item.get("unit"), "Unidade do portal"),
            "quantity_milli": quantity, "unit_price_cents": price,
            "discount_cents": discount, "total_cents": line_total,
        })
    if total <= 0 or total > MAX_SAFE:
        raise ValueError("Total da nota deve ser positivo e estar no intervalo permitido.")
    if "expected_total" not in order or money_to_cents(order["expected_total"]) != total:
        raise ValueError("Total informado não confere com os itens; revise o pedido.")
    notes = str(order.get("notes") or "").strip()
    if len(notes) > 1500:
        raise ValueError("Observação limitada a 1500 caracteres nesta versão.")
    plan = {
        "schema_version": 1, "reference": _text(order.get("reference"), "Referência"),
        "issuer_document": issuer,
        "portal_origin": f"https://{issuer}.emissornfe.sebrae.com.br",
        "customer": {"document": document, "name": _text(customer.get("name"), "Destinatário")},
        "issue_date": _date(order.get("issue_date"), "Emissão"),
        "delivery_date": _date(order.get("delivery_date"), "Entrega"),
        "operation": order["operation"], "cfop": "5102", "presence": PRESENCE[presence],
        "payment": "PIX", "freight_mode": "Sem Ocorrência de Transporte",
        "freight_cents": 0, "items": items, "total_cents": total,
        "notes": notes, "mode": "DRAFT_ONLY",
    }
    plan["request_hash"] = fingerprint(plan)
    return plan


def verify_plan(plan):
    """Reconstruct the normalized plan rather than trusting exported amounts."""
    if not isinstance(plan, dict):
        raise ValueError("Plano deve ser um objeto.")
    try:
        order = {
            key: plan[key] for key in (
                "reference", "issuer_document", "customer", "issue_date", "delivery_date",
                "operation", "cfop", "payment", "freight_mode", "notes",
            )
        }
        order.update(presence=plan["presence"].split(" - ")[0], expected_total=format_money(plan["total_cents"]))
        order["items"] = [{
            "portal_code": i["portal_code"], "description": i["description"], "unit": i["unit"],
            "quantity": format_quantity(i["quantity_milli"]),
            "unit_price": format_money(i["unit_price_cents"]), "discount": format_money(i["discount_cents"]),
        } for i in plan["items"]]
        rebuilt = build_plan(order)
    except (KeyError, TypeError, AttributeError, OverflowError):
        raise ValueError("Estrutura do plano inválida.") from None
    if canonical(rebuilt) != canonical(plan):
        raise ValueError("Plano alterado, incompleto ou checksum inválido.")
    return plan


def order_from_local_invoice(invoice, config):
    if invoice["status"] not in {"DRAFT", "READY_TO_ISSUE"}:
        raise ValueError("Somente notas locais não emitidas podem ser exportadas.")
    order = {**config, "reference": invoice["reference"],
             "customer": {"document": invoice["customer_document"], "name": invoice["customer_name"]},
             "expected_total": invoice["invoice_total"], "notes": invoice.get("notes") or "", "items": []}
    mapping = config.get("products", {})
    for item in invoice["items"]:
        portal = mapping.get(item["product_code"])
        if not isinstance(portal, dict):
            raise ValueError(f"Mapeamento explícito do portal ausente para {item['product_code']}.")
        if normalize_text(portal.get("description")) != normalize_text(item["description"]):
            raise ValueError("Descrição do mapeamento diverge do produto local.")
        if normalize_text(portal.get("unit")) != normalize_text(item["unit"]):
            raise ValueError("Unidade do mapeamento diverge do produto local; conversão automática não suportada.")
        order["items"].append({**portal, "quantity": item["quantity"],
                               "unit_price": item["unit_price"], "discount": item["discount"]})
    return order


def write_plan(plan, destination):
    verify_plan(plan)
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
    except FileExistsError:
        existing = json.loads(path.read_text(encoding="utf-8"))
        if canonical(existing) != canonical(plan):
            raise ValueError("Arquivo de saída já existe com outro pedido; não foi sobrescrito.") from None
    return path


def verify_result(plan, result):
    verify_plan(plan)
    if not isinstance(result, dict):
        raise ValueError("Resultado deve ser um objeto JSON.")
    if result.get("request_hash") != plan["request_hash"]:
        raise ValueError("Resultado pertence a outro plano.")
    if result.get("status") != "SAVED_DRAFT" or result.get("issued") is not False:
        raise ValueError("Resultado não confirma um rascunho salvo; confira o portal antes de repetir.")
    portal_id = str(result.get("portal_id", ""))
    url = f"{plan['portal_origin']}/index-sebrae.html#/invoice/detail/{portal_id}"
    if not portal_id.isdigit() or int(portal_id) <= 0 or result.get("portal_url") != url:
        raise ValueError("Identificador/URL do rascunho inválido.")
    if (type(result.get("total_cents")) is not int or type(result.get("item_count")) is not int
            or result["total_cents"] != plan["total_cents"] or result["item_count"] != len(plan["items"])):
        raise ValueError("Resultado não confere com o total/itens do plano.")
    return {"status": "SAVED_DRAFT", "portal_id": portal_id, "portal_url": url,
            "issued": False, "stock_changed": False,
            "note": "Conferência estrutural de um recibo local; não é consulta nem autorização da SEFAZ."}
