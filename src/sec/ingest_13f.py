"""Download, parse, validate, and store 13F filings."""

import argparse
from pathlib import Path

from src.database.database import connect, initialize_database
from src.sec.client import SECClient
from src.sec.discover_13f import discover_13f, locate_information_table
from src.sec.funds import SEC_ENTITIES
from src.sec.parse_13f import parse_information_table

ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = ROOT / "data" / "raw" / "13f"


def raw_dir(fund_slug: str, reporting_date: str, accession: str) -> Path:
    return RAW_ROOT / fund_slug / reporting_date / accession


def save_bytes(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def get_or_create_security(conn, holding):
    if holding.cusip:
        row = conn.execute("SELECT id FROM securities WHERE cusip = ?", (holding.cusip,)).fetchone()
        if row:
            conn.execute(
                "UPDATE securities SET company_name=?, figi=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (holding.issuer_name, holding.figi, row[0]),
            )
            return row[0]
    if holding.figi:
        row = conn.execute("SELECT id FROM securities WHERE figi = ?", (holding.figi,)).fetchone()
        if row:
            return row[0]
    cur = conn.execute(
        "INSERT INTO securities (company_name, cusip, figi) VALUES (?, ?, ?)",
        (holding.issuer_name, holding.cusip, holding.figi),
    )
    return cur.lastrowid


def ingest_one(client, conn, fund_id: int, fund_slug: str, filing):
    filing = locate_information_table(client, filing)
    folder = raw_dir(fund_slug, filing.reporting_date, filing.accession_number)

    index_bytes = client.get(filing.index_url).content
    info_bytes = client.get(filing.information_table_url).content
    submission_url = filing.index_url.replace("-index.html", ".txt")
    submission_bytes = client.get(submission_url).content

    save_bytes(folder / "filing-index.html", index_bytes)
    save_bytes(folder / "information-table.xml", info_bytes)
    save_bytes(folder / "submission.txt", submission_bytes)

    holdings = parse_information_table(info_bytes)
    if not holdings:
        raise ValueError("Filing parsed successfully but contained zero holdings")

    sec_url = filing.index_url
    conn.execute(
        """
        INSERT INTO filings_13f
          (fund_id, accession_number, filing_date, reporting_date, form_type, sec_cik, sec_url, raw_file_path, filing_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'parsed')
        ON CONFLICT(accession_number) DO UPDATE SET
          filing_date=excluded.filing_date,
          reporting_date=excluded.reporting_date,
          form_type=excluded.form_type,
          sec_cik=excluded.sec_cik,
          sec_url=excluded.sec_url,
          raw_file_path=excluded.raw_file_path,
          filing_status='parsed'
        """,
        (fund_id, filing.accession_number, filing.filing_date, filing.reporting_date,
         filing.form_type, filing.cik, sec_url, str(folder.relative_to(ROOT))),
    )
    filing_id = conn.execute(
        "SELECT id FROM filings_13f WHERE accession_number = ?", (filing.accession_number,)
    ).fetchone()[0]
    conn.execute("DELETE FROM holdings_13f WHERE filing_id = ?", (filing_id,))

    for holding in holdings:
        security_id = get_or_create_security(conn, holding)
        conn.execute(
            """
            INSERT INTO holdings_13f
              (filing_id, security_id, issuer_name, title_of_class, cusip, figi,
               value_dollars, shares_or_principal, shares_or_principal_type, put_call,
               investment_discretion, other_manager, sole_voting, shared_voting,
               none_voting, raw_xml_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (filing_id, security_id, holding.issuer_name, holding.title_of_class,
             holding.cusip, holding.figi, holding.value_dollars,
             holding.shares_or_principal, holding.shares_or_principal_type,
             holding.put_call, holding.investment_discretion, holding.other_manager,
             holding.sole_voting, holding.shared_voting, holding.none_voting,
             holding.raw_xml_hash),
        )

    conn.execute(
        "INSERT INTO ingestion_log (source, accession_number, status, message) VALUES (?, ?, ?, ?)",
        ("SEC 13F", filing.accession_number, "success", f"Stored {len(holdings)} holdings"),
    )
    return len(holdings)


def ingest_fund(client, fund_slug: str, limit: int = 1):
    initialize_database()
    entities = [e for e in SEC_ENTITIES[fund_slug] if e.get("include_in_13f", e.get("role") == "primary")]
    with connect() as conn:
        fund = conn.execute("SELECT id FROM funds WHERE slug = ?", (fund_slug,)).fetchone()
        if not fund:
            raise RuntimeError(f"Fund is not seeded: {fund_slug}")
        fund_id = fund[0]

        for entity in entities:
            cik = entity["cik"]
            filings = discover_13f(client, cik, limit=None)
            # Prefer the latest reporting period, and if there are multiple filings
            # for that period, keep the latest amendment/filing date.
            filings.sort(key=lambda f: (f.reporting_date, f.filing_date, f.form_type), reverse=True)
            if limit:
                filings = filings[:limit]
            for filing in filings:
                try:
                    ingest_one(client, conn, fund_id, fund_slug, filing)
                except Exception as exc:
                    conn.execute(
                        "INSERT INTO ingestion_log (source, accession_number, status, message) VALUES (?, ?, ?, ?)",
                        ("SEC 13F", filing.accession_number, "error", str(exc)),
                    )
                    raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fund", choices=sorted(SEC_ENTITIES), action="append")
    parser.add_argument("--all", action="store_true", help="Process all discovered 13F-HR/HRA filings instead of latest only.")
    args = parser.parse_args()

    client = SECClient()
    funds = args.fund or sorted(SEC_ENTITIES)
    for fund_slug in funds:
        print(f"Ingesting {fund_slug}...")
        ingest_fund(client, fund_slug, limit=None if args.all else 1)
        print(f"Finished {fund_slug}.")


if __name__ == "__main__":
    main()
