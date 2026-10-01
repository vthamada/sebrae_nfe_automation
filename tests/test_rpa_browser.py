"""DOM integration on an intercepted, synthetic portal. No live portal calls."""
import json
import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright
from src.rpa_plan import build_plan

ROOT = Path(__file__).resolve().parents[1]


class RpaBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close(); cls.pw.stop()

    def setUp(self):
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        self.context.route("**/*", self.route)
        order = json.loads((ROOT / "examples/pedido_rpa.json").read_text(encoding="utf-8"))
        order["presence"]="9"; order["items"][0].update(quantity="4",unit_price="29.90")
        order["expected_total"]="119.60"
        self.plan = build_plan(order)
        self.page.goto(self.plan["portal_origin"] + "/index-sebrae.html#/invoice/new")
        self.inject()

    def route(self, route):
        if route.request.url.split("#")[0] == "https://11222333000181.emissornfe.sebrae.com.br/index-sebrae.html":
            route.fulfill(path=str(ROOT / "tests/fixtures/rpa_portal.html"),content_type="text/html")
        else:
            route.abort()

    def inject(self):
        for file in ("protocol.js","runner.js"):
            self.page.add_script_tag(path=str(ROOT / "extension" / file))

    def run_op(self, op):
        return self.page.evaluate("([op,p])=>SebraeDraftRpa.execute(op,p)",[op,self.plan])

    def tearDown(self):
        self.context.close()

    def test_fill_save_reload_confirm_without_emission(self):
        self.assertEqual("EMPTY_FORM_CONFIRMED",self.run_op("CHECK")["status"])
        result=self.run_op("FILL")
        self.assertNotIn("error",result,result)
        self.assertEqual(11960,result["total_cents"])
        self.assertEqual("true",self.page.locator("body").get_attribute("data-product-loaded"))
        self.assertEqual("1250",self.page.locator("body").get_attribute("data-catalog-price"))
        base=self.run_op("SAVE_BASE");self.assertEqual("123",base["portal_id"],base)
        final=self.run_op("FINALIZE");self.assertNotIn("error",final,final)
        self.assertEqual("2",self.page.locator("body").get_attribute("data-saves"))
        self.assertIsNone(self.page.locator("body").get_attribute("data-emitted"))
        self.page.reload();self.inject()
        self.assertEqual("SAVED_DRAFT",self.run_op("RECHECK")["status"])
        self.assertIsNone(self.page.locator("body").get_attribute("data-emitted"))

    def test_dirty_form_blocked(self):
        self.page.locator('[placeholder="Nome do cliente ou fornecedor"]').fill("OUTRO")
        result=self.run_op("FILL")
        self.assertIn("error",result)
        self.assertEqual("0",self.page.locator("body").get_attribute("data-saves"))

    def test_missing_ncm_blocks_before_save(self):
        self.page.evaluate("document.body.dataset.missingNcm='true'")
        result=self.run_op("FILL")
        self.assertIn("NCM",result["error"])
        self.assertEqual("0",self.page.locator("body").get_attribute("data-saves"))

    def test_emitted_existing_page_and_unknown_command_blocked(self):
        self.page.evaluate("location.hash='#/invoice/detail/19'")
        self.assertIn("error",self.run_op("FILL"))
        self.assertIn("error",self.run_op("EMIT"))
        self.assertIsNone(self.page.locator("body").get_attribute("data-emitted"))


if __name__ == "__main__":
    unittest.main()
