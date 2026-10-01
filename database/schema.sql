PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS funds (
    id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL UNIQUE,
    founded_year INTEGER,
    description TEXT,
    headquarters TEXT,
    website TEXT,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS strategy_tags (
    id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE IF NOT EXISTS fund_strategy_tags (
    fund_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (fund_id, tag_id),
    FOREIGN KEY (fund_id) REFERENCES funds(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES strategy_tags(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS fund_performance (
    id INTEGER PRIMARY KEY,
    fund_id INTEGER NOT NULL,
    period_type TEXT NOT NULL CHECK (period_type IN ('since_inception','5_year','3_year')),
    return_rate REAL,
    as_of_date TEXT,
    source TEXT,
    notes TEXT,
    UNIQUE (fund_id, period_type),
    FOREIGN KEY (fund_id) REFERENCES funds(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS fund_sec_entities (
    id INTEGER PRIMARY KEY,
    fund_id INTEGER NOT NULL,
    cik TEXT NOT NULL,
    legal_name TEXT,
    role TEXT NOT NULL DEFAULT 'primary',
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
    UNIQUE (fund_id, cik),
    FOREIGN KEY (fund_id) REFERENCES funds(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS securities (
    id INTEGER PRIMARY KEY,
    ticker TEXT,
    company_name TEXT NOT NULL,
    cusip TEXT,
    exchange TEXT,
    figi TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (cusip),
    UNIQUE (figi)
);

CREATE TABLE IF NOT EXISTS filings_13f (
    id INTEGER PRIMARY KEY,
    fund_id INTEGER NOT NULL,
    accession_number TEXT NOT NULL UNIQUE,
    filing_date TEXT NOT NULL,
    reporting_date TEXT NOT NULL,
    form_type TEXT NOT NULL,
    sec_cik TEXT,
    sec_url TEXT,
    raw_file_path TEXT,
    filing_status TEXT NOT NULL DEFAULT 'parsed',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (fund_id) REFERENCES funds(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_13f_fund_reporting ON filings_13f(fund_id, reporting_date DESC);

CREATE TABLE IF NOT EXISTS holdings_13f (
    id INTEGER PRIMARY KEY,
    filing_id INTEGER NOT NULL,
    security_id INTEGER,
    issuer_name TEXT NOT NULL,
    title_of_class TEXT,
    cusip TEXT,
    figi TEXT,
    value_dollars INTEGER,
    shares_or_principal INTEGER,
    shares_or_principal_type TEXT,
    put_call TEXT,
    investment_discretion TEXT,
    other_manager TEXT,
    sole_voting INTEGER,
    shared_voting INTEGER,
    none_voting INTEGER,
    raw_xml_hash TEXT,
    FOREIGN KEY (filing_id) REFERENCES filings_13f(id) ON DELETE CASCADE,
    FOREIGN KEY (security_id) REFERENCES securities(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_13f_holdings_filing ON holdings_13f(filing_id);
CREATE INDEX IF NOT EXISTS idx_13f_holdings_security ON holdings_13f(security_id);

CREATE TABLE IF NOT EXISTS filings_13d (
    id INTEGER PRIMARY KEY,
    fund_id INTEGER NOT NULL,
    security_id INTEGER,
    accession_number TEXT NOT NULL UNIQUE,
    filing_date TEXT NOT NULL,
    form_type TEXT NOT NULL,
    amendment_number INTEGER,
    shares_owned REAL,
    ownership_percentage REAL,
    cusip TEXT,
    sec_url TEXT,
    raw_file_path TEXT,
    purpose_text TEXT,
    filing_status TEXT NOT NULL DEFAULT 'parsed',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (fund_id) REFERENCES funds(id) ON DELETE CASCADE,
    FOREIGN KEY (security_id) REFERENCES securities(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_13d_fund_date ON filings_13d(fund_id, filing_date DESC);
CREATE INDEX IF NOT EXISTS idx_13d_security_date ON filings_13d(security_id, filing_date DESC);

CREATE TABLE IF NOT EXISTS "13d_events" (
    id INTEGER PRIMARY KEY,
    filing_id INTEGER NOT NULL,
    event_type TEXT,
    previous_shares REAL,
    new_shares REAL,
    previous_percentage REAL,
    new_percentage REAL,
    FOREIGN KEY (filing_id) REFERENCES filings_13d(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ingestion_log (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    accession_number TEXT,
    status TEXT NOT NULL,
    message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Canonical 13F filing for each fund/reporting period.
-- Amendments and original filings are retained in filings_13f, but analytics
-- should use only the latest filing submitted for each reporting period.
CREATE VIEW IF NOT EXISTS latest_13f_by_period AS
SELECT
    id,
    fund_id,
    accession_number,
    filing_date,
    reporting_date,
    form_type,
    sec_cik,
    sec_url,
    raw_file_path,
    filing_status
FROM (
    SELECT
        f.*,
        ROW_NUMBER() OVER (
            PARTITION BY f.fund_id, f.reporting_date
            ORDER BY f.filing_date DESC, f.form_type DESC, f.id DESC
        ) AS rn
    FROM filings_13f AS f
)
WHERE rn = 1;
