from src.repository import (
    add_customer,
    add_product,
    adjust_stock,
    get_product,
    list_low_stock_products,
    list_price_history,
    list_stock_movements,
    update_product,
)
from tests.support import DatabaseTestCase


class ProductAndCustomerTests(DatabaseTestCase):
    def test_product_price_history_and_stock_ledger(self):
        product_id = add_product(
            {
                "internal_code": "prod-001",
                "description": "Produto Teste",
                "unit": "UN",
                "cost_price": "7,50",
                "sale_price": "10,90",
                "stock_qty": "5",
                "min_stock": "2",
                "ncm": "12345678",
            }
        )
        self.assertGreater(product_id, 0)
        product = get_product("PROD-001")
        self.assertEqual(product["sale_price"], "10.90")
        self.assertEqual(product["stock_qty"], "5.000")
        self.assertEqual(product["available_stock"], "5.000")

        update_product("PROD-001", {"sale_price": "11,25"}, reason="REAJUSTE")
        adjust_stock("PROD-001", "-3", reason="CONTAGEM")
        product = get_product("PROD-001")
        self.assertEqual(product["sale_price"], "11.25")
        self.assertEqual(product["stock_qty"], "2.000")
        self.assertEqual(len(list_low_stock_products()), 1)
        self.assertEqual(len(list_price_history("PROD-001")), 2)
        self.assertEqual(len(list_stock_movements("PROD-001")), 2)

    def test_stock_cannot_become_negative(self):
        add_product(
            {
                "internal_code": "PROD-001",
                "description": "Produto",
                "unit": "UN",
                "sale_price": "10",
                "stock_qty": "1",
            }
        )
        with self.assertRaises(ValueError):
            adjust_stock("PROD-001", "-2", reason="ERRO")

    def test_customer_document_is_validated_and_normalized(self):
        customer_id = add_customer(
            {
                "document": "529.982.247-25",
                "legal_name": "Cliente Teste",
                "email": "cliente@example.com",
                "state": "MG",
            }
        )
        self.assertGreater(customer_id, 0)
        with self.assertRaises(ValueError):
            add_customer({"document": "123", "legal_name": "Inválido"})
