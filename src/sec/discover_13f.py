"""Discover 13F filings from SEC submissions JSON."""

from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup

from src.sec.client import SECClient


@dataclass(frozen=True)
class FilingRecord:
    cik: str
    accession_number: str
    filing_date: str
    reporting_date: str
    form_type: str
    primary_document: str
    sec_url: str
    index_url: str
    information_table_url: Optional[str] = None


def submissions_url(cik: str) -> str:
    return f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"


def filing_index_url(cik: str, accession: str) -> str:
    accession_nodash = accession.replace("-", "")
    return (
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
        f"{accession_nodash}/{accession}-index.html"
    )


def _filing_records_from_submissions(cik: str, data: dict) -> list[FilingRecord]:
    recent = data.get("filings", {}).get("recent", {})
    records = []

    for i, form in enumerate(recent.get("form", [])):
        if form not in {"13F-HR", "13F-HR/A"}:
            continue

        accession = recent["accessionNumber"][i]
        filing_date = recent["filingDate"][i]
        reporting_date = recent["reportDate"][i]
        primary_document = recent["primaryDocument"][i]
        index_url = filing_index_url(cik, accession)

        records.append(
            FilingRecord(
                cik=f"{int(cik):010d}",
                accession_number=accession,
                filing_date=filing_date,
                reporting_date=reporting_date,
                form_type=form,
                primary_document=primary_document,
                sec_url=index_url,
                index_url=index_url,
            )
        )

    return records


def discover_13f(client: SECClient, cik: str, limit: Optional[int] = None) -> list[FilingRecord]:
    """Discover 13F-HR/HRA filings across the complete SEC submission history.

    The main submissions JSON contains a recent filing history and, when older
    filings exist, references additional historical JSON files in
    "filings.files". We load both sources so limit=None really means all
    available 13F filings for the CIK.
    """
    data = client.get_json(submissions_url(cik))
    records = _filing_records_from_submissions(cik, data)

    # The SEC submissions endpoint keeps the most recent filings in the main
    # JSON and exposes older history through separate JSON files.
    for historical_file in data.get("filings", {}).get("files", []):
        name = historical_file.get("name")
        if not name:
            continue

        historical_url = f"https://data.sec.gov/submissions/{name}"
        historical_data = client.get_json(historical_url)
        records.extend(_filing_records_from_submissions(cik, historical_data))

    # Historical files and the recent section can overlap. Deduplicate by
    # accession number so each filing is ingested only once.
    unique = {}
    for record in records:
        unique[record.accession_number] = record

    records = list(unique.values())
    records.sort(
        key=lambda f: (f.reporting_date, f.filing_date, f.form_type),
        reverse=True,
    )

    if limit:
        records = records[:limit]

    return records


def locate_information_table(client: SECClient, filing: FilingRecord) -> FilingRecord:
    html = client.get(filing.index_url).text
    soup = BeautifulSoup(html, "html.parser")

    info_url = None

    # SEC filing indexes may contain multiple INFORMATION TABLE rows:
    # one for the XSL-rendered document and one for the raw XML.
    # Select the direct/root-level XML and ignore XSL-rendered XML.
    for row in soup.select("table.tableFile tr"):
        cells = row.find_all("td")
        if not cells:
            continue

        description = " ".join(
            c.get_text(" ", strip=True) for c in cells
        ).upper()

        if "INFORMATION TABLE" not in description:
            continue

        for link in row.find_all("a", href=True):
            href = link["href"]
            normalized = href.lower().split("?", 1)[0]

            if not normalized.endswith(".xml"):
                continue
            if "xslform13f_" in normalized:
                continue

            if href.startswith("/"):
                info_url = "https://www.sec.gov" + href
            elif href.startswith("http"):
                info_url = href
            else:
                info_url = filing.index_url.rsplit("/", 1)[0] + "/" + href

            break

        # Do NOT break merely because an INFORMATION TABLE row was found.
        # Continue until we find the direct/root-level XML.
        if info_url:
            break

    if not info_url:
        # Older EDGAR filings sometimes use a different table layout. Fall
        # back to scanning all document links for the raw information-table
        # XML, while excluding the cover-page XML and XSL-rendered XML.
        for link in soup.find_all("a", href=True):
            href = link["href"]
            normalized = href.lower().split("?", 1)[0]
            if not normalized.endswith(".xml"):
                continue
            if "xslform13f_" in normalized:
                continue
            if normalized.endswith("/primary_doc.xml") or normalized.endswith("primary_doc.xml"):
                continue
            if href.startswith("/"):
                info_url = "https://www.sec.gov" + href
            elif href.startswith("http"):
                info_url = href
            else:
                info_url = filing.index_url.rsplit("/", 1)[0] + "/" + href
            break

    if not info_url:
        raise RuntimeError(
            f"Could not locate raw information table XML for "
            f"{filing.accession_number}"
        )

    return FilingRecord(
        **{**filing.__dict__, "information_table_url": info_url}
    )
