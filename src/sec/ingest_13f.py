"""Download, parse, validate, and store 13F filings."""

import argparse
from pathlib import Path

from src.database.database import connect, initialize_database
from src.sec.client import SECClient
from src.sec.discover_13f import discover_13f, locate_information_table
from src.sec.funds import SEC_ENTITIES
from src.sec.parse_13f import parse_information_table, parse_legacy_information_table

ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = ROOT / "data" / "raw" / "13f"


def raw_dir(fund_slug: str, reporting_date: str, accession: str) -> Path:
    return RAW_ROOT / fund_slug / reporting_date / accession


def save_bytes(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def get_or_create_security(conn, holding):
    cusip_row = None
    figi_row = None

    if holding.cusip:
        cusip_row = conn.execute(
            "SELECT id, figi FROM securities WHERE cusip = ?",
            (holding.cusip,),
        ).fetchone()

    if holding.figi:
        figi_row = conn.execute(
            "SELECT id FROM securities WHERE figi = ?",
            (holding.figi,),
        ).fetchone()

    if cusip_row:
        security_id = cusip_row[0]

        if not cusip_row[1] and not figi_row:
            conn.execute(
                "UPDATE securities SET figi=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (holding.figi, security_id),
            )

        conn.execute(
            "UPDATE securities SET company_name=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (holding.issuer_name, security_id),
        )
        return security_id

    if figi_row:
        return figi_row[0]

    cur = conn.execute(
        "INSERT INTO securities (company_name, cusip, figi) VALUES (?, ?, ?)",
        (holding.issuer_name, holding.cusip, holding.figi),
    )
    return cur.lastrowid


def ingest_one(client, conn, fund_id: int, fund_slug: str, filing, reparse: bool = False):
    existing = conn.execute(
        "SELECT id, filing_status FROM filings_13f WHERE accession_number = ?",
        (filing.accession_number,),
    ).fetchone()
    if existing and existing["filing_status"] == "parsed" and not reparse:
        return 0

    filing = locate_information_table(client, filing)
    folder = raw_dir(fund_slug, filing.reporting_date, filing.accession_number)

    index_path = folder / "filing-index.html"
    submission_path = folder / "submission.txt"
    info_path = folder / "information-table.xml"
    legacy_info_path = folder / "information-table.txt"

    if index_path.exists():
        index_bytes = index_path.read_bytes()
    else:
        index_bytes = client.get(filing.index_url).content
        save_bytes(index_path, index_bytes)

    if submission_path.exists():
        submission_bytes = submission_path.read_bytes()
    else:
        submission_url = filing.index_url.replace("-index.html", ".txt")
        submission_bytes = client.get(submission_url).content
        save_bytes(submission_path, submission_bytes)

    if filing.information_table_url:
        if info_path.exists():
            info_bytes = info_path.read_bytes()
        else:
            info_bytes = client.get(filing.information_table_url).content
            save_bytes(info_path, info_bytes)
        value_multiplier = 1 if filing.reporting_date >= "2023-01-01" else 1000
        holdings = parse_information_table(info_bytes, value_multiplier=value_multiplier)
    else:
        # Pre-2013 13F-HR filings used legacy plaintext information tables.
        # Preserve the complete submission and a copy under an explicit legacy
        # filename so the raw source format remains clear.
        if legacy_info_path.exists():
            legacy_bytes = legacy_info_path.read_bytes()
        else:
            legacy_bytes = submission_bytes
            save_bytes(legacy_info_path, legacy_bytes)
        holdings = parse_legacy_information_table(legacy_bytes)

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


def ingest_fund(client, fund_slug: str, limit: int = 1, reparse: bool = False) -> list[str]:
    initialize_database()
    entities = [e for e in SEC_ENTITIES[fund_slug] if e.get("include_in_13f", e.get("role") == "primary")]
    errors = []
    with connect() as conn:
        fund = conn.execute("SELECT id FROM funds WHERE slug = ?", (fund_slug,)).fetchone()
        if not fund:
            raise RuntimeError(f"Fund is not seeded: {fund_slug}")
        fund_id = fund[0]

        for entity in entities:
            cik = entity["cik"]
            filings = discover_13f(client, cik, limit=None)
            filings.sort(key=lambda f: (f.reporting_date, f.filing_date, f.form_type), reverse=True)
            if limit:
                filings = filings[:limit]
            for filing in filings:
                savepoint = "ingest_filing"
                conn.execute(f"SAVEPOINT {savepoint}")
                try:
                    ingest_one(client, conn, fund_id, fund_slug, filing, reparse=reparse)
                    conn.execute(f"RELEASE SAVEPOINT {savepoint}")
                    conn.commit()
                except Exception as exc:
                    conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                    conn.execute(f"RELEASE SAVEPOINT {savepoint}")
                    conn.execute(
                        "INSERT INTO ingestion_log (source, accession_number, status, message) VALUES (?, ?, ?, ?)",
                        ("SEC 13F", filing.accession_number, "error", str(exc)),
                    )
                    conn.commit()
                    errors.append(f"{fund_slug} {filing.accession_number}: {exc}")
                    print(f"ERROR: {errors[-1]}")

    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fund", choices=sorted(SEC_ENTITIES), action="append")
    parser.add_argument("--all", action="store_true", help="Process all discovered 13F-HR/HRA filings instead of latest only.")
    parser.add_argument("--reparse", action="store_true", help="Re-download/parse filings already marked parsed. Use with --all to rebuild historical data with the current parser.")
    args = parser.parse_args()

    client = SECClient()
    funds = args.fund or sorted(SEC_ENTITIES)
    errors = []
    for fund_slug in funds:
        print(f"Ingesting {fund_slug}...")
        errors.extend(ingest_fund(client, fund_slug, limit=None if args.all else 1))
        print(f"Finished {fund_slug}.")

    if errors:
        print("\nSEC ingestion completed with errors:")
        for error in errors:
            print(f" - {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
