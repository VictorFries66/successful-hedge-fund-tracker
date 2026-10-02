# Successful Hedge Fund Investment Tracker

Foundation for a GitHub-hosted tracker of 8 hedge-fund entities, SEC 13F/13D filings, historical holdings, and cross-fund analysis.

Tracked entities: Citadel, D.E. Shaw, Millennium, TCI, Pershing Square, Elliott, AQR, Lone Pine.

## Current SEC ingestion

The project now has a 13F ingestion pipeline that:

1. discovers Form 13F-HR and 13F-HR/A filings from SEC EDGAR submissions data;
2. limits the project to filings submitted on or after May 20, 2013, the SEC's XML transition date;
3. identifies the filing's Information Table XML;
4. preserves the raw filing materials under `data/raw/13f/`;
5. parses the complete Information Table into SQLite; and
5. records ingestion results in `ingestion_log`.

The website's eight fund entities are kept separate from SEC legal entities. This matters for combination/notice filings; for example, Pershing Square's current primary 13F filer is Pershing Square Inc., while Pershing Square Capital Management is retained as a related SEC entity rather than treated as a ninth fund.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SEC_USER_AGENT="Your Name your-email@example.com"
python -m src.database.seed
python -m src.sec.ingest_13f
```

To ingest every discovered 13F-HR/HRA filing for the tracked primary SEC entities instead of only the latest filing:

```bash
python -m src.sec.ingest_13f --all
```

The SEC User-Agent should identify the application and a contact email.

## SEC data design

The database stores the complete 13F Information Table fields needed for holdings analysis, while the raw filing materials are retained for provenance and parser reprocessing. The historical scope begins at the SEC's May 20, 2013 XML transition; the filing date is the cutoff, not the reporting period. This intentionally excludes the pre-transition ASCII/fixed-width 13F format. Current SEC Form 13F XML specifications use dollar values rather than the older thousand-dollar convention; the database therefore stores `value_dollars` explicitly.

The database retains original and amended 13F accessions, while the `latest_13f_by_period` view selects the latest filing for each fund and reporting period for quarter-to-quarter analysis.
