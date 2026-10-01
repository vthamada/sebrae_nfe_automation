import re
import unicodedata

from src.validators import digits_only, money_to_cents, quantity_to_milli


def match_key(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", text.upper()).split())


def _email_key(value):
    return str(value or "").strip().lower()


def _portal_bool(value):
    return match_key(value) in {"SIM", "ATIVO", "TRUE", "1"}


def _single_index(rows, key_function):
    index = {}
    for position, row in enumerate(rows):
        key = key_function(row)
        if key:
            index.setdefault(key, []).append((position, row))
    return index


def _product_candidate(portal, local_by_barcode, local_by_description):
    barcode = digits_only(portal.get("barcode"))
    if barcode and len(local_by_barcode.get(barcode, [])) == 1:
        return local_by_barcode[barcode], "barcode"
    description = match_key(portal.get("description"))
    candidates = local_by_description.get(description, [])
    return candidates, "description"


def reconcile_products(local_products, portal_products):
    local_by_barcode = _single_index(
        local_products, lambda row: digits_only(row.get("barcode"))
    )
    local_by_description = _single_index(
        local_products, lambda row: match_key(row.get("description"))
    )
    matched_local = set()
    matched = []
    portal_only = []
    ambiguous = []
    differences = []

    for portal in portal_products:
        candidates, matched_by = _product_candidate(
            portal, local_by_barcode, local_by_description
        )
        available = [item for item in candidates if item[0] not in matched_local]
        if not candidates:
            portal_only.append(portal)
            continue
        if len(available) != 1:
            ambiguous.append(
                {
                    "portal": portal,
                    "matched_by": matched_by,
                    "candidate_codes": [
                        row.get("internal_code") for _, row in candidates
                    ],
                }
            )
            continue

        position, local = available[0]
        matched_local.add(position)
        field_differences = {}
        if portal.get("sale_price") not in (None, ""):
            portal_price = money_to_cents(portal["sale_price"])
            local_price = int(local.get("sale_price_cents", 0))
            if portal_price != local_price:
                field_differences["sale_price_cents"] = {
                    "local": local_price,
                    "portal": portal_price,
                }
        for field in ("category", "subcategory"):
            if match_key(local.get(field)) != match_key(portal.get(field)):
                field_differences[field] = {
                    "local": local.get(field),
                    "portal": portal.get(field),
                }
        if portal.get("active") not in (None, ""):
            portal_active = _portal_bool(portal["active"])
            local_active = bool(local.get("active", 1))
            if portal_active != local_active:
                field_differences["active"] = {
                    "local": local_active,
                    "portal": portal_active,
                }

        match = {
            "local_code": local.get("internal_code"),
            "description": portal.get("description"),
            "matched_by": matched_by,
        }
        matched.append(match)
        if field_differences:
            differences.append({**match, "fields": field_differences})

    local_only = [
        row for position, row in enumerate(local_products) if position not in matched_local
    ]
    return {
        "matched": matched,
        "portal_only": portal_only,
        "local_only": local_only,
        "ambiguous": ambiguous,
        "differences": differences,
    }


def reconcile_customers(local_customers, portal_customers):
    local_by_email = _single_index(
        local_customers, lambda row: _email_key(row.get("email"))
    )
    local_by_name = _single_index(
        local_customers, lambda row: match_key(row.get("legal_name"))
    )
    matched_local = set()
    matched = []
    portal_only = []
    ambiguous = []
    differences = []

    for portal in portal_customers:
        email = _email_key(portal.get("email"))
        name = match_key(portal.get("name"))
        candidates = local_by_email.get(email, []) if email else []
        matched_by = "email"
        if not candidates:
            candidates = local_by_name.get(name, [])
            matched_by = "name"
        available = [item for item in candidates if item[0] not in matched_local]
        if not candidates:
            portal_only.append(portal)
            continue
        if len(available) != 1:
            ambiguous.append(
                {
                    "portal": portal,
                    "matched_by": matched_by,
                    "candidate_documents": [row.get("document") for _, row in candidates],
                }
            )
            continue

        position, local = available[0]
        matched_local.add(position)
        field_differences = {}
        if _email_key(local.get("email")) != email:
            field_differences["email"] = {
                "local": local.get("email"),
                "portal": portal.get("email"),
            }
        if digits_only(local.get("phone")) != digits_only(portal.get("phone")):
            field_differences["phone"] = {
                "local": local.get("phone"),
                "portal": portal.get("phone"),
            }
        match = {
            "local_document": local.get("document"),
            "name": portal.get("name"),
            "matched_by": matched_by,
        }
        matched.append(match)
        if field_differences:
            differences.append({**match, "fields": field_differences})

    local_only = [
        row for position, row in enumerate(local_customers) if position not in matched_local
    ]
    return {
        "matched": matched,
        "portal_only": portal_only,
        "local_only": local_only,
        "ambiguous": ambiguous,
        "differences": differences,
    }


def reconcile_stock(local_products, portal_stock_rows, *, complete):
    local_by_description = _single_index(
        local_products, lambda row: match_key(row.get("description"))
    )
    matched = []
    portal_only = []
    ambiguous = []
    differences = []
    for portal in portal_stock_rows:
        candidates = local_by_description.get(match_key(portal.get("product")), [])
        if not candidates:
            portal_only.append(portal)
            continue
        if len(candidates) != 1:
            ambiguous.append(
                {
                    "portal": portal,
                    "candidate_codes": [row.get("internal_code") for _, row in candidates],
                }
            )
            continue
        _, local = candidates[0]
        portal_balance = quantity_to_milli(
            portal.get("balance", "0"), allow_zero=True, allow_negative=True
        )
        local_balance = int(local.get("stock_qty_milli", 0))
        match = {
            "local_code": local.get("internal_code"),
            "product": portal.get("product"),
        }
        matched.append(match)
        if portal_balance != local_balance:
            differences.append(
                {
                    **match,
                    "local_stock_milli": local_balance,
                    "portal_stock_milli": portal_balance,
                }
            )
    return {
        "complete": bool(complete),
        "matched": matched,
        "portal_only": portal_only,
        "ambiguous": ambiguous,
        "differences": differences,
    }


def build_reconciliation(local_products, local_customers, snapshot):
    products = reconcile_products(local_products, snapshot["products"]["rows"])
    customers = reconcile_customers(local_customers, snapshot["clients"]["rows"])
    stock = reconcile_stock(
        local_products,
        snapshot["stock"]["rows"],
        complete=snapshot["stock"].get("complete", False),
    )
    blockers = []
    if not local_products and snapshot["products"]["rows"]:
        blockers.append("Banco local sem produtos; carga inicial deve ser revisada.")
    if not local_customers and snapshot["clients"]["rows"]:
        blockers.append("Banco local sem clientes; documentos não existem no relatório.")
    if not stock["complete"]:
        blockers.append("Snapshot de estoque parcial; não aplicar saldos automaticamente.")
    if products["ambiguous"] or customers["ambiguous"] or stock["ambiguous"]:
        blockers.append("Existem correspondências ambíguas que exigem revisão humana.")
    return {
        "snapshot": {
            "captured_at": snapshot.get("capturedAt"),
            "products_complete": snapshot["products"].get("complete", False),
            "clients_complete": snapshot["clients"].get("complete", False),
            "stock_complete": snapshot["stock"].get("complete", False),
        },
        "local_counts": {
            "products": len(local_products),
            "customers": len(local_customers),
        },
        "products": products,
        "customers": customers,
        "stock": stock,
        "blockers": blockers,
        "safe_to_apply": not blockers,
    }


def compact_summary(report):
    return {
        "snapshot": report["snapshot"],
        "local_counts": report["local_counts"],
        "products": {
            key: len(report["products"][key])
            for key in ("matched", "portal_only", "local_only", "ambiguous", "differences")
        },
        "customers": {
            key: len(report["customers"][key])
            for key in ("matched", "portal_only", "local_only", "ambiguous", "differences")
        },
        "stock": {
            "complete": report["stock"]["complete"],
            **{
                key: len(report["stock"][key])
                for key in ("matched", "portal_only", "ambiguous", "differences")
            },
        },
        "blockers": report["blockers"],
        "safe_to_apply": report["safe_to_apply"],
    }
