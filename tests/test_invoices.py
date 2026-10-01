from src.repository import (
    add_customer,
    add_product,
    cancel_invoice,
    create_invoice_draft,
    get_invoice,
    get_product,
    list_invoices_to_issue,
    mark_invoice_ready,
    record_invoice_emitted,
    update_product,
)
from tests.support import DatabaseTestCase


class InvoiceWorkflowTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        add_customer({"document": "52998224725", "legal_name": "Cliente Teste"})
        add_product(
            {
                "internal_code": "PROD-001",
                "description": "Produto Teste",
                "unit": "UN",
                "sale_price": "12,50",
                "stock_qty": "10",
                "min_stock": "2",
            }
        )

    def test_draft_reserves_stock_and_freezes_price(self):
        invoice = create_invoice_draft(
            reference="PED-001",
            customer_document="52998224725",
            items=[{"product_code": "PROD-001", "quantity": "2"}],
        )
        self.assertEqual(invoice["status"], "DRAFT")
        self.assertEqual(invoice["invoice_total"], "25.00")
        self.assertEqual(get_product("PROD-001")["available_stock"], "8.000")

        update_product("PROD-001", {"sale_price": "20"}, reason="NOVA TABELA")
        self.assertEqual(get_invoice(invoice["id"])["items"][0]["unit_price"], "12.50")

    def test_ready_invoice_is_listed_and_emission_deducts_stock(self):
        invoice = create_invoice_draft(
            reference="PED-002",
            customer_document="52998224725",
            items=[{"product_code": "PROD-001", "quantity": "3"}],
        )
        mark_invoice_ready(invoice["id"])
        self.assertEqual([row["reference"] for row in list_invoices_to_issue()], ["PED-002"])

        emitted = record_invoice_emitted(
            invoice["id"],
            invoice_number="123",
            access_key=("1" * 43) + "2",
        )
        self.assertEqual(emitted["status"], "EMITTED")
        product = get_product("PROD-001")
        self.assertEqual(product["stock_qty"], "7.000")
        self.assertEqual(product["reserved_stock"], "0.000")

    def test_cancel_before_emission_releases_reservation(self):
        invoice = create_invoice_draft(
            reference="PED-003",
            customer_document="52998224725",
            items=[{"product_code": "PROD-001", "quantity": "4"}],
        )
        cancel_invoice(invoice["id"], reason="PEDIDO CANCELADO")
        self.assertEqual(get_product("PROD-001")["available_stock"], "10.000")

    def test_insufficient_stock_rolls_back_entire_invoice(self):
        with self.assertRaises(ValueError):
            create_invoice_draft(
                reference="PED-004",
                customer_document="52998224725",
                items=[{"product_code": "PROD-001", "quantity": "11"}],
            )
        self.assertEqual(get_product("PROD-001")["reserved_stock"], "0.000")

    def test_invoice_reference_is_idempotent(self):
        first = create_invoice_draft(
            reference="PED-005",
            customer_document="52998224725",
            items=[{"product_code": "PROD-001", "quantity": "1"}],
        )
        second = create_invoice_draft(
            reference="PED-005",
            customer_document="52998224725",
            items=[{"product_code": "PROD-001", "quantity": "1"}],
        )
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(get_product("PROD-001")["reserved_stock"], "1.000")

        with self.assertRaises(ValueError):
            create_invoice_draft(
                reference="PED-005",
                customer_document="52998224725",
                items=[
                    {
                        "product_code": "PROD-001",
                        "quantity": "1",
                        "unit_price": "99,00",
                    }
                ],
            )
