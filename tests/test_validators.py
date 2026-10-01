from decimal import Decimal
import unittest

from src.validators import (
    money_to_cents,
    normalize_document,
    normalize_text,
    quantity_to_milli,
    validate_document,
    validate_money,
    validate_ncm,
    validate_nfe_access_key,
)


class ValidatorTests(unittest.TestCase):
    def test_money_rejects_non_finite_values(self):
        for value in ("Infinity", "-Infinity", "NaN", "1e309"):
            with self.subTest(value=value):
                self.assertFalse(validate_money(value))

    def test_money_accepts_brazilian_format_and_converts_exactly(self):
        self.assertTrue(validate_money("1.234,56"))
        self.assertEqual(money_to_cents("1.234,56"), 123456)
        self.assertEqual(money_to_cents(Decimal("10.99")), 1099)

    def test_quantity_uses_exact_milliunits(self):
        self.assertEqual(quantity_to_milli("1,250"), 1250)
        with self.assertRaises(ValueError):
            quantity_to_milli("1.2345")

    def test_normalizers_accept_spreadsheet_scalar_values(self):
        self.assertEqual(normalize_text(123), "123")
        self.assertEqual(normalize_document(52998224725), "52998224725")
        self.assertTrue(validate_ncm(12345678))

    def test_cpf_and_cnpj_check_digits(self):
        self.assertTrue(validate_document("529.982.247-25"))
        self.assertTrue(validate_document("11.222.333/0001-81"))
        self.assertFalse(validate_document("529.982.247-24"))
        self.assertFalse(validate_document("11.111.111/1111-11"))

    def test_nfe_access_key_check_digit(self):
        self.assertTrue(validate_nfe_access_key(("1" * 43) + "2"))
        self.assertFalse(validate_nfe_access_key("1" * 44))


if __name__ == "__main__":
    unittest.main()
