import unittest

from src.sec.ingest_13f import value_multiplier_for_filing


class Test13FValueUnits(unittest.TestCase):
    def test_pre_cutoff_xml_values_are_thousands(self):
        self.assertEqual(value_multiplier_for_filing("2022-12-30"), 1000)

    def test_cutoff_date_uses_dollars(self):
        self.assertEqual(value_multiplier_for_filing("2023-01-03"), 1)

    def test_post_cutoff_amendment_uses_dollars_even_for_old_period(self):
        self.assertEqual(value_multiplier_for_filing("2023-02-14"), 1)

    def test_verified_lone_pine_exception_uses_dollars(self):
        self.assertEqual(
            value_multiplier_for_filing(
                "2015-02-17",
                "0000902664-15-001107",
            ),
            1,
        )

    def test_verified_millennium_exceptions_use_thousands(self):
        for accession in (
            "0001273087-23-000097",
            "0001273087-23-000113",
        ):
            self.assertEqual(
                value_multiplier_for_filing("2023-02-14", accession),
                1000,
            )


if __name__ == "__main__":
    unittest.main()
