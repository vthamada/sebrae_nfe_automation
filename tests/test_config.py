import unittest

from src.config import PRODUCTION_HOST, validate_sebrae_url


class ConfigSecurityTests(unittest.TestCase):
    def test_rejects_http_and_unknown_hosts(self):
        with self.assertRaises(ValueError):
            validate_sebrae_url(
                "http://emissornfe.sebrae.com.br/",
                allowed_hosts=(PRODUCTION_HOST,),
                allow_production=True,
            )
        with self.assertRaises(ValueError):
            validate_sebrae_url(
                "https://sebrae.example.com/",
                allowed_hosts=(PRODUCTION_HOST,),
                allow_production=True,
            )

    def test_production_requires_explicit_opt_in(self):
        with self.assertRaises(RuntimeError):
            validate_sebrae_url(
                "https://emissornfe.sebrae.com.br/",
                allowed_hosts=(PRODUCTION_HOST,),
                allow_production=False,
            )
        self.assertEqual(
            validate_sebrae_url(
                "https://emissornfe.sebrae.com.br/",
                allowed_hosts=(PRODUCTION_HOST,),
                allow_production=True,
            ),
            "https://emissornfe.sebrae.com.br/",
        )
