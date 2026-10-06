import sqlite3
import unittest

from src.analysis.fund_detail import fund_detail
from src.analysis.holdings import latest_positions, position_changes, top_positions
from src.analysis.overlap import portfolio_overlap


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE funds (
                id INTEGER PRIMARY KEY,
                slug TEXT NOT NULL,
                name TEXT NOT NULL
            );
            CREATE TABLE filings_13f (
                id INTEGER PRIMARY KEY,
                fund_id INTEGER NOT NULL,
                filing_date TEXT NOT NULL,
                reporting_date TEXT NOT NULL,
                form_type TEXT NOT NULL
            );
            CREATE TABLE holdings_13f (
                id INTEGER PRIMARY KEY,
                filing_id INTEGER NOT NULL,
                issuer_name TEXT NOT NULL,
                title_of_class TEXT,
                cusip TEXT,
                figi TEXT,
                value_dollars INTEGER,
                shares_or_principal INTEGER,
                shares_or_principal_type TEXT,
                put_call TEXT
            );
            CREATE VIEW latest_13f_by_period AS
            SELECT *
            FROM filings_13f;
        """)
        self.conn.executemany(
            "INSERT INTO funds VALUES (?, ?, ?)",
            [(1, "alpha", "Alpha"), (2, "beta", "Beta")],
        )
        self.conn.executemany(
            "INSERT INTO filings_13f VALUES (?, ?, ?, ?, ?)",
            [
                (1, 1, "2026-05-15", "2026-03-31", "13F-HR"),
                (2, 1, "2026-08-15", "2026-06-30", "13F-HR"),
                (3, 2, "2026-08-15", "2026-06-30", "13F-HR"),
            ],
        )
        self.conn.executemany(
            """
            INSERT INTO holdings_13f
            (id, filing_id, issuer_name, title_of_class, cusip, value_dollars,
             shares_or_principal, shares_or_principal_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, 1, "Common Co", "COM", "111111111", 400, 40, "SH"),
                (2, 1, "Old Co", "COM", "222222222", 600, 60, "SH"),
                (3, 2, "Common Co", "COM", "111111111", 600, 50, "SH"),
                (4, 2, "New Co", "COM", "333333333", 400, 20, "SH"),
                (5, 3, "Common Co", "COM", "111111111", 300, 25, "SH"),
                (6, 3, "Other Co", "COM", "444444444", 700, 70, "SH"),
            ],
        )

    def tearDown(self):
        self.conn.close()

    def test_top_positions_and_portfolio_weights(self):
        positions = top_positions(self.conn, "alpha")
        self.assertEqual([p.issuer_name for p in positions], ["Common Co", "New Co"])
        self.assertAlmostEqual(positions[0].portfolio_weight, 0.6)
        self.assertAlmostEqual(positions[1].portfolio_weight, 0.4)

    def test_position_changes_classify_new_reduced_and_exited(self):
        changes = position_changes(self.conn, "alpha", "2026-06-30")
        by_issuer = {c.issuer_name: c for c in changes}

        self.assertEqual(by_issuer["Common Co"].classification, "increased")
        self.assertEqual(by_issuer["Common Co"].shares_change, 10)
        self.assertEqual(by_issuer["New Co"].classification, "new")
        self.assertEqual(by_issuer["Old Co"].classification, "exited")
        self.assertEqual(by_issuer["Old Co"].value_change_dollars, -600)


    def test_fund_detail_contains_filing_metadata_top_positions_and_changes(self):
        detail = fund_detail(self.conn, "alpha")
        self.assertEqual(detail.name, "Alpha")
        self.assertEqual(detail.reporting_date, "2026-06-30")
        self.assertEqual(detail.form_type, "13F-HR")
        self.assertEqual([p.issuer_name for p in detail.top_positions], ["Common Co", "New Co"])
        self.assertEqual(detail.position_changes[0].classification, "increased")

    def test_overlap_finds_common_holdings(self):
        overlap = portfolio_overlap(self.conn, "2026-06-30")
        self.assertEqual(len(overlap), 1)
        self.assertEqual(overlap[0].issuer_name, "Common Co")
        self.assertEqual(overlap[0].fund_slugs, ("alpha", "beta"))
        self.assertEqual(overlap[0].total_value_dollars, 900)


if __name__ == "__main__":
    unittest.main()
