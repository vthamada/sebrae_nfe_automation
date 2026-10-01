import sqlite3
from contextlib import contextmanager

from src.config import settings


SCHEMA_VERSION = 2

SCHEMA = r"""
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    internal_code TEXT NOT NULL UNIQUE,
    barcode TEXT UNIQUE,
    description TEXT NOT NULL,
    unit TEXT NOT NULL,
    category TEXT,
    subcategory TEXT,
    brand TEXT,
    model TEXT,
    tags TEXT,
    cost_price_cents INTEGER NOT NULL DEFAULT 0 CHECK (cost_price_cents >= 0),
    sale_price_cents INTEGER NOT NULL DEFAULT 0 CHECK (sale_price_cents >= 0),
    stock_qty_milli INTEGER NOT NULL DEFAULT 0 CHECK (stock_qty_milli >= 0),
    reserved_stock_milli INTEGER NOT NULL DEFAULT 0
        CHECK (reserved_stock_milli >= 0 AND reserved_stock_milli <= stock_qty_milli),
    min_stock_milli INTEGER NOT NULL DEFAULT 0 CHECK (min_stock_milli >= 0),
    ncm TEXT,
    cest TEXT,
    cfop TEXT,
    origin TEXT,
    characteristic TEXT NOT NULL DEFAULT 'MERCADORIA PARA REVENDA',
    classification TEXT NOT NULL DEFAULT 'COMUM',
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    moves_stock INTEGER NOT NULL DEFAULT 1 CHECK (moves_stock IN (0, 1)),
    sebrae_synced INTEGER NOT NULL DEFAULT 0 CHECK (sebrae_synced IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document TEXT NOT NULL UNIQUE,
    legal_name TEXT NOT NULL,
    trade_name TEXT,
    state_registration TEXT,
    email TEXT,
    phone TEXT,
    zip_code TEXT,
    street TEXT,
    number TEXT,
    complement TEXT,
    neighborhood TEXT,
    city TEXT,
    state TEXT,
    country TEXT NOT NULL DEFAULT 'BRASIL',
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    sebrae_synced INTEGER NOT NULL DEFAULT 0 CHECK (sebrae_synced IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reference TEXT NOT NULL UNIQUE,
    customer_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT', 'READY_TO_ISSUE', 'EMITTED', 'CANCELLED')),
    products_total_cents INTEGER NOT NULL DEFAULT 0 CHECK (products_total_cents >= 0),
    discount_total_cents INTEGER NOT NULL DEFAULT 0 CHECK (discount_total_cents >= 0),
    invoice_total_cents INTEGER NOT NULL DEFAULT 0 CHECK (invoice_total_cents >= 0),
    notes TEXT,
    invoice_number TEXT,
    access_key TEXT,
    cancellation_reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    issued_at TEXT,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE IF NOT EXISTS invoice_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity_milli INTEGER NOT NULL CHECK (quantity_milli > 0),
    unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0),
    discount_cents INTEGER NOT NULL DEFAULT 0 CHECK (discount_cents >= 0),
    total_cents INTEGER NOT NULL CHECK (total_cents >= 0),
    FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    old_price_cents INTEGER,
    new_price_cents INTEGER NOT NULL CHECK (new_price_cents >= 0),
    reason TEXT NOT NULL,
    changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS stock_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    invoice_id INTEGER,
    movement_type TEXT NOT NULL
        CHECK (movement_type IN ('INITIAL', 'ADJUSTMENT', 'RESERVATION', 'RELEASE', 'ISSUE')),
    on_hand_delta_milli INTEGER NOT NULL DEFAULT 0,
    reserved_delta_milli INTEGER NOT NULL DEFAULT 0,
    on_hand_after_milli INTEGER NOT NULL CHECK (on_hand_after_milli >= 0),
    reserved_after_milli INTEGER NOT NULL CHECK (reserved_after_milli >= 0),
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id),
    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
);

CREATE TABLE IF NOT EXISTS automation_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    details TEXT,
    screenshot_path TEXT,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT
);
"""

INVARIANT_TRIGGERS = r"""
CREATE TRIGGER IF NOT EXISTS trg_products_stock_insert
BEFORE INSERT ON products
WHEN NEW.stock_qty_milli < 0
  OR NEW.reserved_stock_milli < 0
  OR NEW.reserved_stock_milli > NEW.stock_qty_milli
BEGIN
    SELECT RAISE(ABORT, 'invalid product stock invariant');
END;

CREATE TRIGGER IF NOT EXISTS trg_products_stock_update
BEFORE UPDATE OF stock_qty_milli, reserved_stock_milli ON products
WHEN NEW.stock_qty_milli < 0
  OR NEW.reserved_stock_milli < 0
  OR NEW.reserved_stock_milli > NEW.stock_qty_milli
BEGIN
    SELECT RAISE(ABORT, 'invalid product stock invariant');
END;

CREATE TRIGGER IF NOT EXISTS trg_invoices_status_insert
BEFORE INSERT ON invoices
WHEN NEW.status NOT IN ('DRAFT', 'READY_TO_ISSUE', 'EMITTED', 'CANCELLED')
BEGIN
    SELECT RAISE(ABORT, 'invalid invoice status');
END;

CREATE TRIGGER IF NOT EXISTS trg_invoices_status_update
BEFORE UPDATE OF status ON invoices
WHEN NEW.status NOT IN ('DRAFT', 'READY_TO_ISSUE', 'EMITTED', 'CANCELLED')
BEGIN
    SELECT RAISE(ABORT, 'invalid invoice status');
END;

CREATE TRIGGER IF NOT EXISTS trg_invoices_totals_insert
BEFORE INSERT ON invoices
WHEN NEW.products_total_cents < 0
  OR NEW.discount_total_cents < 0
  OR NEW.invoice_total_cents < 0
  OR NEW.discount_total_cents > NEW.products_total_cents
  OR NEW.invoice_total_cents != NEW.products_total_cents - NEW.discount_total_cents
BEGIN
    SELECT RAISE(ABORT, 'invalid invoice totals');
END;

CREATE TRIGGER IF NOT EXISTS trg_invoices_totals_update
BEFORE UPDATE OF products_total_cents, discount_total_cents, invoice_total_cents ON invoices
WHEN NEW.products_total_cents < 0
  OR NEW.discount_total_cents < 0
  OR NEW.invoice_total_cents < 0
  OR NEW.discount_total_cents > NEW.products_total_cents
  OR NEW.invoice_total_cents != NEW.products_total_cents - NEW.discount_total_cents
BEGIN
    SELECT RAISE(ABORT, 'invalid invoice totals');
END;

CREATE TRIGGER IF NOT EXISTS trg_invoice_items_values_insert
BEFORE INSERT ON invoice_items
WHEN NEW.quantity_milli <= 0
  OR NEW.unit_price_cents < 0
  OR NEW.discount_cents < 0
  OR NEW.total_cents < 0
BEGIN
    SELECT RAISE(ABORT, 'invalid invoice item values');
END;
"""


def _columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _ensure_column(conn, table, name, definition):
    if name not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _migrate_legacy_schema(conn):
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version >= SCHEMA_VERSION:
        return

    product_columns = _columns(conn, "products")
    _ensure_column(conn, "products", "cost_price_cents", "INTEGER NOT NULL DEFAULT 0 CHECK (cost_price_cents >= 0)")
    _ensure_column(conn, "products", "sale_price_cents", "INTEGER NOT NULL DEFAULT 0 CHECK (sale_price_cents >= 0)")
    _ensure_column(conn, "products", "stock_qty_milli", "INTEGER NOT NULL DEFAULT 0 CHECK (stock_qty_milli >= 0)")
    _ensure_column(conn, "products", "reserved_stock_milli", "INTEGER NOT NULL DEFAULT 0 CHECK (reserved_stock_milli >= 0)")
    _ensure_column(conn, "products", "min_stock_milli", "INTEGER NOT NULL DEFAULT 0 CHECK (min_stock_milli >= 0)")
    if "cost_price" in product_columns:
        conn.execute(
            """
            UPDATE products SET
                cost_price_cents = CAST(ROUND(cost_price * 100) AS INTEGER),
                sale_price_cents = CAST(ROUND(sale_price * 100) AS INTEGER),
                stock_qty_milli = CAST(ROUND(stock_qty * 1000) AS INTEGER),
                min_stock_milli = CAST(ROUND(min_stock * 1000) AS INTEGER)
            """
        )

    _ensure_column(conn, "customers", "active", "INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))")

    invoice_columns = _columns(conn, "invoices")
    _ensure_column(conn, "invoices", "reference", "TEXT")
    _ensure_column(conn, "invoices", "products_total_cents", "INTEGER NOT NULL DEFAULT 0 CHECK (products_total_cents >= 0)")
    _ensure_column(conn, "invoices", "discount_total_cents", "INTEGER NOT NULL DEFAULT 0 CHECK (discount_total_cents >= 0)")
    _ensure_column(conn, "invoices", "invoice_total_cents", "INTEGER NOT NULL DEFAULT 0 CHECK (invoice_total_cents >= 0)")
    _ensure_column(conn, "invoices", "invoice_number", "TEXT")
    _ensure_column(conn, "invoices", "access_key", "TEXT")
    _ensure_column(conn, "invoices", "cancellation_reason", "TEXT")
    _ensure_column(conn, "invoices", "updated_at", "TEXT")
    _ensure_column(conn, "invoices", "issued_at", "TEXT")
    conn.execute("UPDATE invoices SET reference = 'LEGACY-' || id WHERE reference IS NULL")
    conn.execute("UPDATE invoices SET updated_at = created_at WHERE updated_at IS NULL")
    if "products_total" in invoice_columns:
        conn.execute(
            """
            UPDATE invoices SET
                products_total_cents = CAST(ROUND(products_total * 100) AS INTEGER),
                discount_total_cents = CAST(ROUND(discount_total * 100) AS INTEGER),
                invoice_total_cents = CAST(ROUND(invoice_total * 100) AS INTEGER)
            """
        )

    item_columns = _columns(conn, "invoice_items")
    _ensure_column(conn, "invoice_items", "quantity_milli", "INTEGER NOT NULL DEFAULT 0 CHECK (quantity_milli >= 0)")
    _ensure_column(conn, "invoice_items", "unit_price_cents", "INTEGER NOT NULL DEFAULT 0 CHECK (unit_price_cents >= 0)")
    _ensure_column(conn, "invoice_items", "discount_cents", "INTEGER NOT NULL DEFAULT 0 CHECK (discount_cents >= 0)")
    _ensure_column(conn, "invoice_items", "total_cents", "INTEGER NOT NULL DEFAULT 0 CHECK (total_cents >= 0)")
    if "quantity" in item_columns:
        conn.execute(
            """
            UPDATE invoice_items SET
                quantity_milli = CAST(ROUND(quantity * 1000) AS INTEGER),
                unit_price_cents = CAST(ROUND(unit_price * 100) AS INTEGER),
                discount_cents = CAST(ROUND(discount * 100) AS INTEGER),
                total_cents = CAST(ROUND(total * 100) AS INTEGER)
            """
        )

    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def init_db():
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path, timeout=30)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        _migrate_legacy_schema(conn)
        conn.executescript(INVARIANT_TRIGGERS)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_invoices_reference ON invoices(reference) WHERE reference IS NOT NULL")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_invoices_access_key ON invoices(access_key) WHERE access_key IS NOT NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_stock_movements_product ON stock_movements(product_id, id)")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_conn():
    conn = sqlite3.connect(settings.db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
