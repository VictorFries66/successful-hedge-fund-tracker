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

def initialize_database(db_path=DB_PATH):
    with connect(db_path) as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
