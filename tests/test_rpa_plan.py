import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.rpa_plan import build_plan, verify_plan, verify_result, write_plan, order_from_local_invoice

ROOT = Path(__file__).resolve().parents[1]


class RpaPlanTests(unittest.TestCase):
    def order(self):
        return json.loads((ROOT / "examples/pedido_rpa.json").read_text(encoding="utf-8"))

    def test_roundtrip(self):
        plan = build_plan(self.order())
        self.assertEqual(2500, plan["total_cents"])
        self.assertEqual("DRAFT_ONLY", plan["mode"])
        self.assertEqual(plan, verify_plan(plan))

    def test_explicit_presence_required(self):
        order = self.order(); del order["presence"]
        with self.assertRaisesRegex(ValueError, "presença"):
            build_plan(order)

    def test_bad_total(self):
        order = self.order(); order["expected_total"] = "24.99"
        with self.assertRaisesRegex(ValueError, "Total"):
            build_plan(order)

    def test_exact_half_up_fractional_quantities(self):
        order = self.order(); order["items"][0].update(quantity="0.005", unit_price="1.00")
        order["expected_total"] = "0.01"
        self.assertEqual(1, build_plan(order)["total_cents"])

    def test_duplicate_code(self):
        order = self.order(); order["items"] *= 2
        with self.assertRaisesRegex(ValueError, "repetido"):
            build_plan(order)

    def test_unknown_operation_and_freight(self):
        for changes in [{"cfop":"6102"}, {"payment":"DINHEIRO"}, {"freight":"1.00"}, {"freight_mode":"CIF"}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                build_plan({**self.order(), **changes})

    def test_invalid_documents_and_dates(self):
        for changes in [{"issuer_document":"00000000000000"}, {"customer":[]}, {"items":[None]}, {"delivery_date":"2026-02-30"}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                build_plan({**self.order(), **changes})

    def test_tampering(self):
        plan = build_plan(self.order())
        for changes in [{"mode":"EMIT"}, {"total_cents":2499}, {"presence":"9 - Operação não presencial, outros"}, {"freight_cents":100}, {"other":True}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                verify_plan({**plan, **changes})

    def test_exclusive_output(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "plan.json"
            plan = build_plan(self.order()); write_plan(plan,path); write_plan(plan,path)
            original = path.read_bytes()
            changed = build_plan({**self.order(), "reference":"OUTRO"})
            with self.assertRaisesRegex(ValueError,"sobrescrito"):
                write_plan(changed,path)
            self.assertEqual(original,path.read_bytes())

    def test_receipt_not_emission(self):
        plan = build_plan(self.order())
        receipt = {"status":"SAVED_DRAFT", "request_hash":plan["request_hash"], "issued":False,
                   "portal_id":"123", "portal_url":plan["portal_origin"]+"/index-sebrae.html#/invoice/detail/123",
                   "total_cents":2500, "item_count":1}
        self.assertFalse(verify_result(plan,receipt)["stock_changed"])
        for changes in [{"issued":True}, {"status":"UNCERTAIN"}, {"portal_id":"456"}, {"total_cents":2501}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                verify_result(plan,{**receipt,**changes})

    def test_cli_prepare_does_not_init_database(self):
        from scripts.manage import main
        with tempfile.TemporaryDirectory() as folder, patch("scripts.manage.init_db") as init:
            main(["rpa-preparar","--pedido",str(ROOT/"examples/pedido_rpa.json"),"--saida",str(Path(folder)/"plan.json")])
            init.assert_not_called()

    def test_local_mapping_required_and_no_reexport_emitted(self):
        invoice = {"status":"DRAFT","reference":"LOCAL-1","customer_document":"52998224725",
                   "customer_name":"CLIENTE TESTE","invoice_total":"25.00","items":[
                       {"product_code":"LOCAL-001","description":"PRODUTO TESTE","unit":"UN","quantity":"2.000",
                        "unit_price":"12.50","discount":"0.00"}]}
        config = self.order()
        with self.assertRaisesRegex(ValueError,"Mapeamento"):
            order_from_local_invoice(invoice,config)
        config["products"] = {"LOCAL-001":{"portal_code":"PORTAL-001","description":"PRODUTO TESTE","unit":"UN"}}
        before = copy.deepcopy(invoice)
        self.assertEqual(2500,build_plan(order_from_local_invoice(invoice,config))["total_cents"])
        self.assertEqual(before,invoice)
        invoice["status"]="EMITTED"
        with self.assertRaises(ValueError): order_from_local_invoice(invoice,config)

    def test_python_javascript_protocol_parity(self):
        plan = build_plan(self.order())
        js = "const P=require('./extension/protocol.js'); let s=''; process.stdin.on('data',x=>s+=x); process.stdin.on('end',()=>P.validate(JSON.parse(s)).then(p=>process.stdout.write(p.request_hash)).catch(e=>{console.error(e.message);process.exitCode=1}));"
        result = subprocess.run(["node","-e",js],input=json.dumps(plan,ensure_ascii=False),text=True,
                                encoding="utf-8",capture_output=True,cwd=ROOT,check=True)
        self.assertEqual(plan["request_hash"],result.stdout)


if __name__ == "__main__":
    unittest.main()
