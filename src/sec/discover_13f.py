"""Discover 13F filings from SEC submissions JSON."""

from dataclasses import dataclass
import re
from typing import Optional

from bs4 import BeautifulSoup

from src.sec.client import SECClient


# The SEC replaced the text-based 13F format with XML on May 20, 2013.
# The tracker intentionally starts at that filing-date boundary, regardless of
# the reporting period covered by a filing.
MIN_FILING_DATE = "2013-05-20"


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

    for historical_file in data.get("filings", {}).get("files", []):
        name = historical_file.get("name")
        if not name:
            continue

        historical_url = f"https://data.sec.gov/submissions/{name}"
        historical_data = client.get_json(historical_url)
        records.extend(_filing_records_from_submissions(cik, historical_data))

    unique = {}
    for record in records:
        unique[record.accession_number] = record

    # Scope the tracker to filings submitted under the post-transition XML
    # system. Use filing_date rather than reporting_date because an amendment
    # for an older reporting period can itself be an XML filing after the cutoff.
    records = [
        record for record in unique.values()
        if record.filing_date >= MIN_FILING_DATE
    ]
    records.sort(
        key=lambda f: (f.reporting_date, f.filing_date, f.form_type),
        reverse=True,
    )

    if limit:
        records = records[:limit]

    return records


def _resolve_document_url(filing: FilingRecord, href: str) -> str:
    if href.startswith("/"):
        return "https://www.sec.gov" + href
    if href.startswith("http"):
        return href
    return filing.index_url.rsplit("/", 1)[0] + "/" + href


def _information_table_from_submission(client: SECClient, filing: FilingRecord) -> Optional[str]:
    """Find the information-table filename from the SEC submission text."""
    submission_url = filing.index_url.replace("-index.html", ".txt")
    response = client.get(submission_url)
    text = response.text

    for block in re.findall(
        r"<DOCUMENT>(.*?)(?=<DOCUMENT>|</SEC-DOCUMENT>)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        doc_type = re.search(
            r"<TYPE>\s*([^\r\n<]+)", block, flags=re.IGNORECASE
        )
        filename = re.search(
            r"<FILENAME>\s*([^\r\n<]+)", block, flags=re.IGNORECASE
        )
        if not doc_type or not filename:
            continue
        if doc_type.group(1).strip().upper() != "INFORMATION TABLE":
            continue

        name = filename.group(1).strip()
        normalized = name.lower().split("?", 1)[0]
        if normalized.endswith(".xml") and "xslform13f_" not in normalized:
            return _resolve_document_url(filing, name)

    return None


def locate_information_table(client: SECClient, filing: FilingRecord) -> FilingRecord:
    html = client.get(filing.index_url).text
    soup = BeautifulSoup(html, "html.parser")

    info_url = None

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

            info_url = _resolve_document_url(filing, href)
            break

        if info_url:
            break

    if not info_url:
        for link in soup.find_all("a", href=True):
            href = link["href"]
            normalized = href.lower().split("?", 1)[0]
            if not normalized.endswith(".xml"):
                continue
            if "xslform13f_" in normalized:
                continue
            if normalized.endswith("/primary_doc.xml") or normalized.endswith("primary_doc.xml"):
                continue

            info_url = _resolve_document_url(filing, href)
            break

    if not info_url:
        try:
            info_url = _information_table_from_submission(client, filing)
        except Exception:
            info_url = None

    if not info_url:
        raise RuntimeError(
            f"Could not locate raw information table XML for "
            f"{filing.accession_number}"
        )

    return FilingRecord(
        **{**filing.__dict__, "information_table_url": info_url}
    )
