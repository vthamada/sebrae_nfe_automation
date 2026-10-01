import sqlite3
from decimal import Decimal, ROUND_HALF_UP

from rapidfuzz import fuzz

from src.database import get_conn
from src.validators import (
    digits_only,
    format_money,
    format_quantity,
    money_to_cents,
    normalize_document,
    normalize_text,
    quantity_to_milli,
    validate_cest,
    validate_cfop,
    validate_customer,
    validate_ncm,
    validate_nfe_access_key,
    validate_product,
)


INVOICE_STATUSES = ("DRAFT", "READY_TO_ISSUE", "EMITTED", "CANCELLED")


def _table_columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _next_internal_code(conn, prefix="PROD-"):
    normalized_prefix = normalize_text(prefix)
    rows = conn.execute(
        "SELECT internal_code FROM products WHERE internal_code LIKE ?",
        (f"{normalized_prefix}%",),
    ).fetchall()
    numbers = []
    for row in rows:
        suffix = row["internal_code"][len(normalized_prefix) :]
        if suffix.isdigit():
            numbers.append(int(suffix))
    return f"{normalized_prefix}{max(numbers, default=0) + 1:03d}"


def next_internal_code(prefix="PROD-"):
    with get_conn() as conn:
        return _next_internal_code(conn, prefix)


def _ean13(stem):
    if len(stem) != 12 or not stem.isdigit():
        raise ValueError("A base do código EAN deve possuir 12 dígitos.")
    checksum = sum(int(char) * (1 if index % 2 == 0 else 3) for index, char in enumerate(stem))
    return stem + str((-checksum) % 10)


def _next_neutral_barcode(conn):
    rows = conn.execute(
        "SELECT barcode FROM products WHERE barcode LIKE '200%'"
    ).fetchall()
    sequences = []
    for row in rows:
        barcode = row["barcode"] or ""
        if len(barcode) == 13 and barcode.isdigit() and barcode.startswith("200"):
            sequences.append(int(barcode[3:12]))
    return _ean13(f"200{max(sequences, default=0) + 1:09d}")


def next_neutral_barcode():
    with get_conn() as conn:
        return _next_neutral_barcode(conn)


def _serialize_product(row):
    if row is None:
        return None
    item = dict(row)
    item["cost_price"] = format_money(item["cost_price_cents"])
    item["sale_price"] = format_money(item["sale_price_cents"])
    item["stock_qty"] = format_quantity(item["stock_qty_milli"])
    item["reserved_stock"] = format_quantity(item["reserved_stock_milli"])
    item["available_stock"] = format_quantity(
        item["stock_qty_milli"] - item["reserved_stock_milli"]
    )
    item["min_stock"] = format_quantity(item["min_stock_milli"])
    return item


def get_product(code_or_barcode):
    value = normalize_text(code_or_barcode)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM products WHERE internal_code = ? OR barcode = ?",
            (value, digits_only(code_or_barcode)),
        ).fetchone()
    if row is None:
        raise ValueError(f"Produto não encontrado: {value}")
    return _serialize_product(row)


def list_products(*, active_only=True):
    query = "SELECT * FROM products"
    params = ()
    if active_only:
        query += " WHERE active = 1"
    query += " ORDER BY description, internal_code"
    with get_conn() as conn:
        return [_serialize_product(row) for row in conn.execute(query, params).fetchall()]


def list_low_stock_products():
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM products
            WHERE active = 1 AND moves_stock = 1
              AND (stock_qty_milli - reserved_stock_milli) <= min_stock_milli
            ORDER BY description, internal_code
            """
        ).fetchall()
    return [_serialize_product(row) for row in rows]


def list_price_history(internal_code):
    code = normalize_text(internal_code)
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT ph.*, p.internal_code
            FROM price_history ph JOIN products p ON p.id = ph.product_id
            WHERE p.internal_code = ? ORDER BY ph.id
            """,
            (code,),
        ).fetchall()
    output = []
    for row in rows:
        item = dict(row)
        item["old_price"] = (
            format_money(item["old_price_cents"])
            if item["old_price_cents"] is not None
            else None
        )
        item["new_price"] = format_money(item["new_price_cents"])
        output.append(item)
    return output


def list_stock_movements(internal_code):
    code = normalize_text(internal_code)
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT sm.*, p.internal_code
            FROM stock_movements sm JOIN products p ON p.id = sm.product_id
            WHERE p.internal_code = ? ORDER BY sm.id
            """,
            (code,),
        ).fetchall()
    output = []
    for row in rows:
        item = dict(row)
        for source, target in (
            ("on_hand_delta_milli", "on_hand_delta"),
            ("reserved_delta_milli", "reserved_delta"),
            ("on_hand_after_milli", "on_hand_after"),
            ("reserved_after_milli", "reserved_after"),
        ):
            item[target] = format_quantity(item[source])
        output.append(item)
    return output


def find_product_candidates(description, threshold=80):
    query = normalize_text(description)
    if not query:
        return []
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM products WHERE active = 1").fetchall()
    output = []
    for row in rows:
        score = fuzz.token_set_ratio(query, normalize_text(row["description"]))
        if score >= threshold:
            item = _serialize_product(row)
            item["similarity"] = score
            output.append(item)
    return sorted(output, key=lambda item: item["similarity"], reverse=True)


def _normalize_tags(tags):
    if isinstance(tags, (list, tuple, set)):
        return ", ".join(normalize_text(tag) for tag in tags if normalize_text(tag)) or None
    return normalize_text(tags) or None


def _record_stock_movement(
    conn,
    product_id,
    movement_type,
    on_hand_delta,
    reserved_delta,
    on_hand_after,
    reserved_after,
    reason,
    invoice_id=None,
):
    conn.execute(
        """
        INSERT INTO stock_movements (
            product_id, invoice_id, movement_type, on_hand_delta_milli,
            reserved_delta_milli, on_hand_after_milli, reserved_after_milli, reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            product_id,
            invoice_id,
            movement_type,
            on_hand_delta,
            reserved_delta,
            on_hand_after,
            reserved_after,
            normalize_text(reason),
        ),
    )


def add_product(product):
    payload = dict(product)
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        payload["internal_code"] = normalize_text(payload.get("internal_code")) or _next_internal_code(conn)
        errors = validate_product(payload)
        if errors:
            raise ValueError(" | ".join(errors))
        barcode = digits_only(payload.get("barcode")) or _next_neutral_barcode(conn)
        if not 8 <= len(barcode) <= 14:
            raise ValueError("Código de barras deve possuir entre 8 e 14 dígitos.")
        cost_cents = money_to_cents(payload.get("cost_price", 0))
        sale_cents = money_to_cents(payload.get("sale_price", 0))
        stock_milli = quantity_to_milli(payload.get("stock_qty", 0), allow_zero=True)
        min_stock_milli = quantity_to_milli(payload.get("min_stock", 0), allow_zero=True)
        moves_stock = bool(payload.get("moves_stock", True))
        if not moves_stock and stock_milli:
            raise ValueError("Produto sem movimentação de estoque deve iniciar com saldo zero.")
        try:
            cursor = conn.execute(
                """
                INSERT INTO products (
                    internal_code, barcode, description, unit, category, subcategory,
                    brand, model, tags, cost_price_cents, sale_price_cents,
                    stock_qty_milli, reserved_stock_milli, min_stock_milli,
                    ncm, cest, cfop, origin, characteristic, classification,
                    active, moves_stock, sebrae_synced
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, 1, ?, 0)
                """,
                (
                    payload["internal_code"],
                    barcode,
                    normalize_text(payload["description"]),
                    normalize_text(payload["unit"]),
                    normalize_text(payload.get("category")) or None,
                    normalize_text(payload.get("subcategory")) or None,
                    normalize_text(payload.get("brand")) or None,
                    normalize_text(payload.get("model")) or None,
                    _normalize_tags(payload.get("tags")),
                    cost_cents,
                    sale_cents,
                    stock_milli,
                    min_stock_milli,
                    digits_only(payload.get("ncm")) or None,
                    digits_only(payload.get("cest")) or None,
                    digits_only(payload.get("cfop")) or None,
                    normalize_text(payload.get("origin")) or None,
                    normalize_text(payload.get("characteristic", "MERCADORIA PARA REVENDA")),
                    normalize_text(payload.get("classification", "COMUM")),
                    1 if moves_stock else 0,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Código interno ou código de barras já cadastrado.") from exc
        product_id = cursor.lastrowid
        conn.execute(
            "INSERT INTO price_history (product_id, old_price_cents, new_price_cents, reason) VALUES (?, NULL, ?, ?)",
            (product_id, sale_cents, "CADASTRO INICIAL"),
        )
        if stock_milli:
            _record_stock_movement(
                conn,
                product_id,
                "INITIAL",
                stock_milli,
                0,
                stock_milli,
                0,
                "ESTOQUE INICIAL",
            )
        return product_id


def update_product(internal_code, changes, *, reason):
    code = normalize_text(internal_code)
    if not normalize_text(reason):
        raise ValueError("Motivo da alteração obrigatório.")
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM products WHERE internal_code = ?", (code,)).fetchone()
        if row is None:
            raise ValueError(f"Produto não encontrado: {code}")
        assignments = []
        values = []
        text_fields = {
            "description": False,
            "unit": False,
            "category": True,
            "subcategory": True,
            "brand": True,
            "model": True,
            "origin": True,
            "characteristic": False,
            "classification": False,
        }
        for field, nullable in text_fields.items():
            if field in changes:
                value = normalize_text(changes[field])
                if not nullable and not value:
                    raise ValueError(f"{field} não pode ficar vazio.")
                assignments.append(f"{field} = ?")
                values.append(value or None)
        if "tags" in changes:
            assignments.append("tags = ?")
            values.append(_normalize_tags(changes["tags"]))
        for field, validator in (("ncm", validate_ncm), ("cest", validate_cest), ("cfop", validate_cfop)):
            if field in changes:
                if not validator(changes[field]):
                    raise ValueError(f"{field.upper()} inválido.")
                assignments.append(f"{field} = ?")
                values.append(digits_only(changes[field]) or None)
        if "barcode" in changes:
            barcode = digits_only(changes["barcode"])
            if barcode and not 8 <= len(barcode) <= 14:
                raise ValueError("Código de barras deve possuir entre 8 e 14 dígitos.")
            assignments.append("barcode = ?")
            values.append(barcode or None)
        old_sale_cents = row["sale_price_cents"]
        new_sale_cents = old_sale_cents
        for public_name, column in (("cost_price", "cost_price_cents"), ("sale_price", "sale_price_cents")):
            if public_name in changes:
                cents = money_to_cents(changes[public_name])
                assignments.append(f"{column} = ?")
                values.append(cents)
                if public_name == "sale_price":
                    new_sale_cents = cents
        if "min_stock" in changes:
            assignments.append("min_stock_milli = ?")
            values.append(quantity_to_milli(changes["min_stock"], allow_zero=True))
        for field in ("active", "moves_stock"):
            if field in changes:
                if field == "moves_stock" and row["reserved_stock_milli"]:
                    raise ValueError("Não é possível alterar controle de estoque com reserva ativa.")
                assignments.append(f"{field} = ?")
                values.append(1 if changes[field] else 0)
        if not assignments:
            raise ValueError("Nenhum campo permitido foi informado para atualização.")
        assignments.append("updated_at = CURRENT_TIMESTAMP")
        try:
            conn.execute(
                f"UPDATE products SET {', '.join(assignments)} WHERE id = ?",
                (*values, row["id"]),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Código de barras já cadastrado.") from exc
        if new_sale_cents != old_sale_cents:
            conn.execute(
                "INSERT INTO price_history (product_id, old_price_cents, new_price_cents, reason) VALUES (?, ?, ?, ?)",
                (row["id"], old_sale_cents, new_sale_cents, normalize_text(reason)),
            )
    return get_product(code)


def adjust_stock(internal_code, quantity_delta, *, reason):
    code = normalize_text(internal_code)
    reason = normalize_text(reason)
    if not reason:
        raise ValueError("Motivo do ajuste de estoque obrigatório.")
    delta = quantity_to_milli(quantity_delta, allow_zero=False, allow_negative=True)
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM products WHERE internal_code = ?", (code,)).fetchone()
        if row is None:
            raise ValueError(f"Produto não encontrado: {code}")
        if not row["moves_stock"]:
            raise ValueError("Este produto não movimenta estoque.")
        new_on_hand = row["stock_qty_milli"] + delta
        if new_on_hand < row["reserved_stock_milli"]:
            raise ValueError("O ajuste deixaria o estoque abaixo da quantidade reservada.")
        conn.execute(
            "UPDATE products SET stock_qty_milli = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_on_hand, row["id"]),
        )
        _record_stock_movement(
            conn,
            row["id"],
            "ADJUSTMENT",
            delta,
            0,
            new_on_hand,
            row["reserved_stock_milli"],
            reason,
        )
    return get_product(code)


def add_customer(customer):
    errors = validate_customer(customer)
    if errors:
        raise ValueError(" | ".join(errors))
    document = normalize_document(customer["document"])
    fields = (
        "trade_name",
        "state_registration",
        "email",
        "phone",
        "zip_code",
        "street",
        "number",
        "complement",
        "neighborhood",
        "city",
        "state",
        "country",
    )
    values = []
    for field in fields:
        value = customer.get(field)
        if field in {"state", "country"}:
            value = normalize_text(value)
        else:
            value = str(value).strip() if value not in (None, "") else None
        if field == "country" and not value:
            value = "BRASIL"
        values.append(value or None)
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            cursor = conn.execute(
                """
                INSERT INTO customers (
                    document, legal_name, trade_name, state_registration, email,
                    phone, zip_code, street, number, complement, neighborhood,
                    city, state, country, active, sebrae_synced
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0)
                """,
                (document, normalize_text(customer["legal_name"]), *values),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("CPF ou CNPJ já cadastrado.") from exc
        return cursor.lastrowid


def get_customer(document):
    normalized = normalize_document(document)
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM customers WHERE document = ?", (normalized,)).fetchone()
    if row is None:
        raise ValueError(f"Cliente não encontrado: {normalized}")
    return dict(row)


def update_customer(document, changes):
    normalized = normalize_document(document)
    allowed = {
        "legal_name",
        "trade_name",
        "state_registration",
        "email",
        "phone",
        "zip_code",
        "street",
        "number",
        "complement",
        "neighborhood",
        "city",
        "state",
        "country",
        "active",
    }
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute("SELECT * FROM customers WHERE document = ?", (normalized,)).fetchone()
        if existing is None:
            raise ValueError(f"Cliente não encontrado: {normalized}")
        candidate = dict(existing)
        candidate.update(changes)
        errors = validate_customer(candidate)
        if errors:
            raise ValueError(" | ".join(errors))
        assignments = []
        values = []
        for field in allowed:
            if field not in changes:
                continue
            value = changes[field]
            if field == "active":
                value = 1 if value else 0
            elif field in {"legal_name", "state", "country"}:
                value = normalize_text(value)
            else:
                value = str(value).strip() if value not in (None, "") else None
            assignments.append(f"{field} = ?")
            values.append(value)
        if not assignments:
            raise ValueError("Nenhum campo permitido foi informado para atualização.")
        assignments.extend(["sebrae_synced = 0", "updated_at = CURRENT_TIMESTAMP"])
        conn.execute(
            f"UPDATE customers SET {', '.join(assignments)} WHERE id = ?",
            (*values, existing["id"]),
        )
    return get_customer(normalized)


def list_customers(*, active_only=True):
    query = "SELECT * FROM customers"
    if active_only:
        query += " WHERE active = 1"
    query += " ORDER BY legal_name, document"
    with get_conn() as conn:
        return [dict(row) for row in conn.execute(query).fetchall()]


def _line_total_cents(unit_price_cents, quantity_milli, discount_cents):
    gross = int(
        (Decimal(unit_price_cents) * Decimal(quantity_milli) / Decimal(1000)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    if discount_cents > gross:
        raise ValueError("Desconto não pode ser maior que o valor bruto do item.")
    return gross, gross - discount_cents


def _serialize_invoice(conn, row):
    invoice = dict(row)
    invoice["products_total"] = format_money(invoice["products_total_cents"])
    invoice["discount_total"] = format_money(invoice["discount_total_cents"])
    invoice["invoice_total"] = format_money(invoice["invoice_total_cents"])
    items = conn.execute(
        """
        SELECT ii.*, p.internal_code AS product_code, p.description, p.unit
        FROM invoice_items ii
        JOIN products p ON p.id = ii.product_id
        WHERE ii.invoice_id = ?
        ORDER BY ii.id
        """,
        (row["id"],),
    ).fetchall()
    invoice["items"] = []
    for item_row in items:
        item = dict(item_row)
        item["quantity"] = format_quantity(item["quantity_milli"])
        item["unit_price"] = format_money(item["unit_price_cents"])
        item["discount"] = format_money(item["discount_cents"])
        item["total"] = format_money(item["total_cents"])
        invoice["items"].append(item)
    return invoice


def get_invoice(invoice_id):
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT i.*, c.document AS customer_document, c.legal_name AS customer_name
            FROM invoices i JOIN customers c ON c.id = i.customer_id
            WHERE i.id = ?
            """,
            (int(invoice_id),),
        ).fetchone()
        if row is None:
            raise ValueError(f"Nota não encontrada: {invoice_id}")
        return _serialize_invoice(conn, row)


def _same_idempotent_request(conn, existing, customer_id, items, notes):
    if existing["customer_id"] != customer_id:
        return False
    normalized_notes = str(notes).strip() if notes else None
    if existing["notes"] != normalized_notes:
        return False
    stored = conn.execute(
        """
        SELECT p.internal_code, ii.quantity_milli, ii.unit_price_cents, ii.discount_cents
        FROM invoice_items ii JOIN products p ON p.id = ii.product_id
        WHERE ii.invoice_id = ? ORDER BY ii.id
        """,
        (existing["id"],),
    ).fetchall()
    if len(stored) != len(items):
        return False
    for row, item in zip(stored, items):
        if row["internal_code"] != normalize_text(item["product_code"]):
            return False
        if row["quantity_milli"] != quantity_to_milli(item["quantity"]):
            return False
        if row["discount_cents"] != money_to_cents(item.get("discount", 0)):
            return False
        if item.get("unit_price") not in (None, ""):
            if row["unit_price_cents"] != money_to_cents(item["unit_price"]):
                return False
    return True


def create_invoice_draft(*, reference, customer_document, items, notes=None):
    reference = normalize_text(reference)
    if not reference:
        raise ValueError("Referência da nota obrigatória.")
    if not items:
        raise ValueError("A nota deve possuir ao menos um item.")
    document = normalize_document(customer_document)
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        customer = conn.execute(
            "SELECT * FROM customers WHERE document = ? AND active = 1", (document,)
        ).fetchone()
        if customer is None:
            raise ValueError(f"Cliente ativo não encontrado: {document}")
        existing = conn.execute("SELECT * FROM invoices WHERE reference = ?", (reference,)).fetchone()
        if existing is not None:
            if not _same_idempotent_request(conn, existing, customer["id"], items, notes):
                raise ValueError("A referência já existe com cliente ou itens diferentes.")
            detail_row = conn.execute(
                """
                SELECT i.*, c.document AS customer_document, c.legal_name AS customer_name
                FROM invoices i JOIN customers c ON c.id = i.customer_id WHERE i.id = ?
                """,
                (existing["id"],),
            ).fetchone()
            return _serialize_invoice(conn, detail_row)

        prepared_items = []
        reservation_by_product = {}
        products_total = discount_total = invoice_total = 0
        for item in items:
            code = normalize_text(item.get("product_code"))
            product = conn.execute(
                "SELECT * FROM products WHERE internal_code = ? AND active = 1", (code,)
            ).fetchone()
            if product is None:
                raise ValueError(f"Produto ativo não encontrado: {code}")
            quantity_milli = quantity_to_milli(item.get("quantity"))
            unit_price_cents = (
                money_to_cents(item["unit_price"])
                if item.get("unit_price") not in (None, "")
                else product["sale_price_cents"]
            )
            discount_cents = money_to_cents(item.get("discount", 0))
            gross_cents, total_cents = _line_total_cents(
                unit_price_cents, quantity_milli, discount_cents
            )
            prepared_items.append(
                (product, quantity_milli, unit_price_cents, discount_cents, total_cents)
            )
            products_total += gross_cents
            discount_total += discount_cents
            invoice_total += total_cents
            if product["moves_stock"]:
                reservation_by_product[product["id"]] = (
                    reservation_by_product.get(product["id"], 0) + quantity_milli
                )

        for product_id, quantity_milli in reservation_by_product.items():
            product = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
            available = product["stock_qty_milli"] - product["reserved_stock_milli"]
            if quantity_milli > available:
                raise ValueError(
                    f"Estoque insuficiente para {product['internal_code']}: "
                    f"disponível {format_quantity(available)}."
                )

        cursor = conn.execute(
            """
            INSERT INTO invoices (
                reference, customer_id, status, products_total_cents,
                discount_total_cents, invoice_total_cents, notes, updated_at
            ) VALUES (?, ?, 'DRAFT', ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                reference,
                customer["id"],
                products_total,
                discount_total,
                invoice_total,
                str(notes).strip() if notes else None,
            ),
        )
        invoice_id = cursor.lastrowid
        legacy_items = {"quantity", "unit_price", "discount", "total"}.issubset(
            _table_columns(conn, "invoice_items")
        )
        for product, quantity_milli, unit_price_cents, discount_cents, total_cents in prepared_items:
            if legacy_items:
                conn.execute(
                    """
                    INSERT INTO invoice_items (
                        invoice_id, product_id, quantity, unit_price, discount, total,
                        quantity_milli, unit_price_cents, discount_cents, total_cents
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        invoice_id,
                        product["id"],
                        quantity_milli / 1000,
                        unit_price_cents / 100,
                        discount_cents / 100,
                        total_cents / 100,
                        quantity_milli,
                        unit_price_cents,
                        discount_cents,
                        total_cents,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO invoice_items (
                        invoice_id, product_id, quantity_milli, unit_price_cents,
                        discount_cents, total_cents
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        invoice_id,
                        product["id"],
                        quantity_milli,
                        unit_price_cents,
                        discount_cents,
                        total_cents,
                    ),
                )
        for product_id, quantity_milli in reservation_by_product.items():
            product = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
            new_reserved = product["reserved_stock_milli"] + quantity_milli
            conn.execute(
                "UPDATE products SET reserved_stock_milli = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_reserved, product_id),
            )
            _record_stock_movement(
                conn,
                product_id,
                "RESERVATION",
                0,
                quantity_milli,
                product["stock_qty_milli"],
                new_reserved,
                f"RESERVA DA NOTA {reference}",
                invoice_id,
            )
    return get_invoice(invoice_id)


def _transition_invoice(invoice_id, expected_status, new_status, extra_sql="", extra_values=()):
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM invoices WHERE id = ?", (int(invoice_id),)).fetchone()
        if row is None:
            raise ValueError(f"Nota não encontrada: {invoice_id}")
        if row["status"] != expected_status:
            raise ValueError(
                f"Transição inválida: nota está em {row['status']}, esperado {expected_status}."
            )
        conn.execute(
            f"UPDATE invoices SET status = ?, updated_at = CURRENT_TIMESTAMP{extra_sql} WHERE id = ?",
            (new_status, *extra_values, int(invoice_id)),
        )
    return get_invoice(invoice_id)


def mark_invoice_ready(invoice_id):
    return _transition_invoice(invoice_id, "DRAFT", "READY_TO_ISSUE")


def list_invoices(*, status=None):
    query = """
        SELECT i.*, c.document AS customer_document, c.legal_name AS customer_name
        FROM invoices i JOIN customers c ON c.id = i.customer_id
    """
    params = ()
    if status:
        normalized_status = normalize_text(status)
        if normalized_status not in INVOICE_STATUSES:
            raise ValueError("Status de nota inválido.")
        query += " WHERE i.status = ?"
        params = (normalized_status,)
    query += " ORDER BY i.id"
    with get_conn() as conn:
        return [_serialize_invoice(conn, row) for row in conn.execute(query, params).fetchall()]


def list_invoices_to_issue():
    return list_invoices(status="READY_TO_ISSUE")


def record_invoice_emitted(invoice_id, *, invoice_number, access_key):
    number = digits_only(invoice_number)
    key = digits_only(access_key)
    if not number:
        raise ValueError("Número da NF-e obrigatório.")
    if not validate_nfe_access_key(key):
        raise ValueError("Chave de acesso da NF-e inválida.")
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        invoice = conn.execute("SELECT * FROM invoices WHERE id = ?", (int(invoice_id),)).fetchone()
        if invoice is None:
            raise ValueError(f"Nota não encontrada: {invoice_id}")
        if invoice["status"] != "READY_TO_ISSUE":
            raise ValueError("Somente uma nota pronta pode ser confirmada como emitida.")
        items = conn.execute(
            """
            SELECT ii.product_id, SUM(ii.quantity_milli) AS quantity_milli, p.*
            FROM invoice_items ii JOIN products p ON p.id = ii.product_id
            WHERE ii.invoice_id = ? GROUP BY ii.product_id
            """,
            (invoice["id"],),
        ).fetchall()
        for product in items:
            if not product["moves_stock"]:
                continue
            quantity = product["quantity_milli"]
            new_on_hand = product["stock_qty_milli"] - quantity
            new_reserved = product["reserved_stock_milli"] - quantity
            if new_on_hand < 0 or new_reserved < 0:
                raise ValueError("Inconsistência de estoque detectada; emissão local não registrada.")
            conn.execute(
                """
                UPDATE products SET stock_qty_milli = ?, reserved_stock_milli = ?,
                    updated_at = CURRENT_TIMESTAMP WHERE id = ?
                """,
                (new_on_hand, new_reserved, product["product_id"]),
            )
            _record_stock_movement(
                conn,
                product["product_id"],
                "ISSUE",
                -quantity,
                -quantity,
                new_on_hand,
                new_reserved,
                f"EMISSÃO DA NOTA {invoice['reference']}",
                invoice["id"],
            )
        try:
            conn.execute(
                """
                UPDATE invoices SET status = 'EMITTED', invoice_number = ?, access_key = ?,
                    issued_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?
                """,
                (number, key, invoice["id"]),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Chave de acesso já registrada em outra nota.") from exc
    return get_invoice(invoice_id)


def cancel_invoice(invoice_id, *, reason):
    reason = normalize_text(reason)
    if not reason:
        raise ValueError("Motivo do cancelamento obrigatório.")
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        invoice = conn.execute("SELECT * FROM invoices WHERE id = ?", (int(invoice_id),)).fetchone()
        if invoice is None:
            raise ValueError(f"Nota não encontrada: {invoice_id}")
        if invoice["status"] not in {"DRAFT", "READY_TO_ISSUE"}:
            raise ValueError("Somente rascunhos ou notas prontas podem ser cancelados localmente.")
        items = conn.execute(
            """
            SELECT ii.product_id, SUM(ii.quantity_milli) AS quantity_milli, p.*
            FROM invoice_items ii JOIN products p ON p.id = ii.product_id
            WHERE ii.invoice_id = ? GROUP BY ii.product_id
            """,
            (invoice["id"],),
        ).fetchall()
        for product in items:
            if not product["moves_stock"]:
                continue
            quantity = product["quantity_milli"]
            new_reserved = product["reserved_stock_milli"] - quantity
            if new_reserved < 0:
                raise ValueError("Inconsistência de reserva detectada; cancelamento não aplicado.")
            conn.execute(
                "UPDATE products SET reserved_stock_milli = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_reserved, product["product_id"]),
            )
            _record_stock_movement(
                conn,
                product["product_id"],
                "RELEASE",
                0,
                -quantity,
                product["stock_qty_milli"],
                new_reserved,
                f"CANCELAMENTO DA NOTA {invoice['reference']}",
                invoice["id"],
            )
        conn.execute(
            """
            UPDATE invoices SET status = 'CANCELLED', cancellation_reason = ?,
                updated_at = CURRENT_TIMESTAMP WHERE id = ?
            """,
            (reason, invoice["id"]),
        )
    return get_invoice(invoice_id)
