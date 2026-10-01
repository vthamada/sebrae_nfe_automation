import unittest

from src.automation.sebrae import PortalMappingRequiredError, SebraeAutomation


class PortalGuardTests(unittest.TestCase):
    def test_portal_mutations_fail_closed_until_mapping_is_homologated(self):
        automation = SebraeAutomation()
        for method, payload in (
            (automation.prepare_product, {}),
            (automation.prepare_customer, {}),
            (automation.prepare_invoice_draft, {}),
        ):
            with self.subTest(method=method.__name__):
                with self.assertRaises(PortalMappingRequiredError):
                    method(payload)
        self.assertIsNone(automation.page)
