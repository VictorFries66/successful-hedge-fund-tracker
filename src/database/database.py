from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "database" / "tracker.db"
SCHEMA_PATH = ROOT / "database" / "schema.sql"

def connect(db_path=DB_PATH):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def _add_column_if_missing(conn, table, column, definition):
    columns = {
        row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def initialize_database(db_path=DB_PATH):
    with connect(db_path) as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

        # Migrate databases created before generic 13F manager metadata was added.
        _add_column_if_missing(conn, "filings_13f", "sec_entity_id", "INTEGER")
        _add_column_if_missing(conn, "filings_13f", "report_type", "TEXT")
        _add_column_if_missing(conn, "filings_13f", "filing_manager_name", "TEXT")
        _add_column_if_missing(conn, "filings_13f", "form_13f_file_number", "TEXT")

        conn.execute("DROP VIEW IF EXISTS latest_13f_by_period")
        conn.execute("""
            CREATE VIEW latest_13f_by_period AS
            SELECT
                id, fund_id, accession_number, filing_date, reporting_date,
                form_type, sec_cik, sec_entity_id, sec_url, raw_file_path,
                filing_status, report_type, filing_manager_name, form_13f_file_number
            FROM (
                SELECT
                    f.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY f.fund_id, f.reporting_date
                        ORDER BY f.filing_date DESC, f.form_type DESC, f.id DESC
                    ) AS rn
                FROM filings_13f AS f
            )
            WHERE rn = 1
        """)
        conn.commit()
