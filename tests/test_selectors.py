import unittest

from src.automation.selectors import CUSTOMER, INVOICE, PRODUCT, ROUTES


class PortalSelectorMapTests(unittest.TestCase):
    def test_confirmed_routes_match_the_mapped_portal(self):
        self.assertEqual(ROUTES["products"], "#/item")
        self.assertEqual(ROUTES["customers"], "#/client")
        self.assertEqual(ROUTES["invoice_new"], "#/invoice/new")
        self.assertEqual(ROUTES["report_stock"], "#/report_stock_kardex")

    def test_confirmed_semantic_selectors_are_present(self):
        self.assertEqual(PRODUCT["tags"]["by"], "placeholder")
        self.assertEqual(PRODUCT["stock_tab"]["name"], "Estoque")
        self.assertEqual(CUSTOMER["zip_code"]["value"], "CEP")
        self.assertEqual(
            INVOICE["customer_search"]["value"],
            "Nome do cliente ou fornecedor",
        )


if __name__ == "__main__":
    unittest.main()
