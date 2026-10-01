"""MV3 bootstrap/IPC smoke in a disposable Chromium profile, not user's Chrome."""
import json
import tempfile
import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright
from src.rpa_plan import build_plan, fingerprint

ROOT = Path(__file__).resolve().parents[1]


class RpaExtensionTests(unittest.TestCase):
    def test_mv3_panel_and_journal_ipc(self):
        order = json.loads((ROOT / "examples/pedido_rpa.json").read_text(encoding="utf-8"))
        plan = build_plan(order)
        journal_key = "draft:" + fingerprint([plan["issuer_document"], plan["reference"]])
        with tempfile.TemporaryDirectory() as profile, sync_playwright() as pw:
            extension = str(ROOT / "extension")
            context = pw.chromium.launch_persistent_context(
                profile, channel="chromium", headless=True,
                args=[f"--disable-extensions-except={extension}", f"--load-extension={extension}",
                      "--disable-background-networking"],
            )
            try:
                # No site content or credentials; the only writable state is this temporary profile.
                context.route("http://**/*", lambda route: route.abort())
                context.route("https://**/*", lambda route: route.abort())
                worker = context.service_workers[0] if context.service_workers else context.wait_for_event("serviceworker")
                worker.evaluate("([key,hash])=>chrome.storage.local.set({[key]:{status:'SAVED_DRAFT',request_hash:hash,issued:false}})",
                                [journal_key,plan["request_hash"]])
                extension_id = worker.url.split("/")[2]
                page = context.new_page()
                page.goto(f"chrome-extension://{extension_id}/panel.html?target=123")
                self.assertEqual("Preparar rascunho NF-e",page.locator("h1").inner_text())
                response = page.evaluate("p=>chrome.runtime.sendMessage({action:'RECEIPT',plan:p,tabId:123})",plan)
                self.assertTrue(response["ok"],response)
                self.assertEqual("SAVED_DRAFT",response["result"]["status"])
                self.assertFalse(response["result"]["issued"])
            finally:
                context.close()


if __name__ == "__main__":
    unittest.main()
