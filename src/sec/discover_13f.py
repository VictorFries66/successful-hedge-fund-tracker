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


def discover_13f(client: SECClient, cik: str, limit: Optional[int] = None) -> list[FilingRecord]:
    data = client.get_json(submissions_url(cik))
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
        records.append(FilingRecord(
            cik=f"{int(cik):010d}",
            accession_number=accession,
            filing_date=filing_date,
            reporting_date=reporting_date,
            form_type=form,
            primary_document=primary_document,
            sec_url=index_url,
            index_url=index_url,
        ))
        if limit and len(records) >= limit:
            break

    return records


def locate_information_table(client: SECClient, filing: FilingRecord) -> FilingRecord:
    html = client.get(filing.index_url).text
    soup = BeautifulSoup(html, "html.parser")

    info_url = None
    for row in soup.select("table.tableFile tr"):
        cells = row.find_all("td")
        if not cells:
            continue
        description = " ".join(c.get_text(" ", strip=True) for c in cells).upper()
        if "INFORMATION TABLE" not in description:
            continue
        link = row.find("a", href=True)
        if link:
            href = link["href"]
            if href.startswith("/"):
                info_url = "https://www.sec.gov" + href
            elif href.startswith("http"):
                info_url = href
            else:
                info_url = filing.index_url.rsplit("/", 1)[0] + "/" + href
            break

    if not info_url:
        # Some EDGAR index layouts expose the information table in the raw HTML
        # without a description cell. Search links as a fallback.
        for link in soup.find_all("a", href=True):
            text = link.get_text(" ", strip=True).lower()
            href = link["href"].lower()
            if "information" in text or "infotable" in href or "informationtable" in href:
                target = link["href"]
                if target.startswith("/"):
                    info_url = "https://www.sec.gov" + target
                elif target.startswith("http"):
                    info_url = target
                else:
                    info_url = filing.index_url.rsplit("/", 1)[0] + "/" + target
                break

    if not info_url:
        raise RuntimeError(f"Could not locate information table for {filing.accession_number}")

    return FilingRecord(**{**filing.__dict__, "information_table_url": info_url})
