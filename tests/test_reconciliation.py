import unittest

from src.reconciliation import build_reconciliation, match_key


class ReconciliationTests(unittest.TestCase):
    def test_matches_accents_and_reports_price_difference(self):
        local = [{
            "internal_code": "P-1",
            "barcode": None,
            "description": "CABO SANTO ÂNGELO",
            "sale_price_cents": 1000,
            "category": "ÁUDIO",
            "subcategory": "CABOS",
            "active": 1,
            "stock_qty_milli": 2000,
        }]
        snapshot = self._snapshot(
            products=[{
                "description": "Cabo Santo Angelo",
                "sale_price": "R$ 12,00",
                "category": "Audio",
                "subcategory": "Cabos",
                "active": "Sim",
            }],
            stock=[{"product": "CABO SANTO ANGELO", "balance": "2"}],
        )
        report = build_reconciliation(local, [], snapshot)

        self.assertEqual(match_key("ÂNGULO"), "ANGULO")
        self.assertEqual(len(report["products"]["matched"]), 1)
        self.assertEqual(
            report["products"]["differences"][0]["fields"]["sale_price_cents"],
            {"local": 1000, "portal": 1200},
        )
        self.assertEqual(report["stock"]["differences"], [])

    def test_empty_local_database_is_blocked_and_never_safe_to_apply(self):
        snapshot = self._snapshot(
            products=[{
                "description": "PRODUTO A",
                "sale_price": "10,00",
                "category": "",
                "subcategory": "",
                "active": "Sim",
            }],
            clients=[{"name": "CLIENTE A", "phone": "", "email": ""}],
            stock=[{"product": "PRODUTO A", "balance": "1"}],
            stock_complete=False,
        )
        report = build_reconciliation([], [], snapshot)

        self.assertEqual(len(report["products"]["portal_only"]), 1)
        self.assertEqual(len(report["customers"]["portal_only"]), 1)
        self.assertEqual(len(report["stock"]["portal_only"]), 1)
        self.assertFalse(report["safe_to_apply"])
        self.assertEqual(len(report["blockers"]), 3)

    def test_duplicate_local_description_is_ambiguous(self):
        local = [
            {"internal_code": "A", "description": "PRODUTO", "barcode": None},
            {"internal_code": "B", "description": "PRODUTO", "barcode": None},
        ]
        snapshot = self._snapshot(products=[{
            "description": "PRODUTO",
            "sale_price": "0,00",
            "category": "",
            "subcategory": "",
            "active": "Sim",
        }])
        report = build_reconciliation(local, [], snapshot)

        self.assertEqual(len(report["products"]["ambiguous"]), 1)
        self.assertFalse(report["safe_to_apply"])

    @staticmethod
    def _snapshot(products=None, clients=None, stock=None, stock_complete=True):
        return {
            "capturedAt": "2026-08-25",
            "products": {"complete": True, "rows": products or []},
            "clients": {"complete": True, "rows": clients or []},
            "stock": {"complete": stock_complete, "rows": stock or []},
        }


if __name__ == "__main__":
    unittest.main()
