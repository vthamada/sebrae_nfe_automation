import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.config import settings
from src.database import SCHEMA_VERSION, init_db


LEGACY_SCHEMA = """
CREATE TABLE products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    internal_code TEXT NOT NULL UNIQUE,
    barcode TEXT UNIQUE,
    description TEXT NOT NULL,
    unit TEXT NOT NULL,
    category TEXT, subcategory TEXT, brand TEXT, model TEXT, tags TEXT,
    cost_price REAL NOT NULL DEFAULT 0,
    sale_price REAL NOT NULL DEFAULT 0,
    stock_qty REAL NOT NULL DEFAULT 0,
    min_stock REAL NOT NULL DEFAULT 0,
    ncm TEXT, cest TEXT, cfop TEXT, origin TEXT,
    characteristic TEXT NOT NULL DEFAULT 'MERCADORIA PARA REVENDA',
    classification TEXT NOT NULL DEFAULT 'COMUM',
    active INTEGER NOT NULL DEFAULT 1,
    moves_stock INTEGER NOT NULL DEFAULT 1,
    sebrae_synced INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document TEXT NOT NULL UNIQUE,
    legal_name TEXT NOT NULL,
    trade_name TEXT, state_registration TEXT, email TEXT, phone TEXT,
    zip_code TEXT, street TEXT, number TEXT, complement TEXT,
    neighborhood TEXT, city TEXT, state TEXT,
    country TEXT NOT NULL DEFAULT 'BRASIL',
    sebrae_synced INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'DRAFT',
    products_total REAL NOT NULL DEFAULT 0,
    discount_total REAL NOT NULL DEFAULT 0,
    invoice_total REAL NOT NULL DEFAULT 0,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);
CREATE TABLE invoice_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity REAL NOT NULL,
    unit_price REAL NOT NULL,
    discount REAL NOT NULL DEFAULT 0,
    total REAL NOT NULL,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id)
);
CREATE TABLE automation_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    details TEXT,
    screenshot_path TEXT,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT
);
"""


class DatabaseMigrationTests(unittest.TestCase):
    def test_migrates_legacy_money_and_stock_without_float_usage_afterward(self):
        original = settings.db_path
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            database = Path(temp_dir) / "legacy.db"
            conn = sqlite3.connect(database)
            try:
                conn.executescript(LEGACY_SCHEMA)
                conn.execute(
                    """
                    INSERT INTO products (
                        internal_code, description, unit, cost_price, sale_price,
                        stock_qty, min_stock
                    ) VALUES ('PROD-001', 'PRODUTO', 'UN', 7.5, 10.9, 3.25, 1)
                    """
                )
                conn.commit()
            finally:
                conn.close()
            object.__setattr__(settings, "db_path", database)
            try:
                init_db()
                conn = sqlite3.connect(database)
                try:
                    row = conn.execute(
                        """
                        SELECT cost_price_cents, sale_price_cents, stock_qty_milli,
                               min_stock_milli, reserved_stock_milli
                        FROM products WHERE internal_code = 'PROD-001'
                        """
                    ).fetchone()
                    self.assertEqual(row, (750, 1090, 3250, 1000, 0))
                    self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
                    with self.assertRaises(sqlite3.IntegrityError):
                        conn.execute(
                            "UPDATE products SET reserved_stock_milli = 4000 WHERE internal_code = 'PROD-001'"
                        )
                finally:
                    conn.close()
            finally:
                object.__setattr__(settings, "db_path", original)


if __name__ == "__main__":
    unittest.main()
