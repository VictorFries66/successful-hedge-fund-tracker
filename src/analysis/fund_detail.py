"""Analysis contract for an individual fund detail page."""

from dataclasses import dataclass
from typing import Optional

from .holdings import Position, PositionChange, position_changes, top_positions


@dataclass(frozen=True)
class FundDetail:
    fund_id: int
    slug: str
    name: str
    reporting_date: str
    filing_id: int
    accession_number: str
    filing_date: str
    form_type: str
    report_type: Optional[str]
    filing_manager_name: Optional[str]
    form_13f_file_number: Optional[str]
    sec_url: Optional[str]
    top_positions: tuple[Position, ...]
    position_changes: tuple[PositionChange, ...]


def fund_detail(conn, fund_slug: str, reporting_date: str | None = None, top_limit: int = 10):
    """Build the complete 13F data needed by a fund detail page."""
    top = top_positions(conn, fund_slug, reporting_date, limit=top_limit)
    if not top:
        return None

    selected_date = top[0].reporting_date
    filing = conn.execute(
        """
        SELECT
            v.fund_id,
            f.slug,
            f.name,
            v.reporting_date,
            v.id AS filing_id,
            v.accession_number,
            v.filing_date,
            v.form_type,
            v.report_type,
            v.filing_manager_name,
            v.form_13f_file_number,
            v.sec_url
        FROM latest_13f_by_period v
        JOIN funds f ON f.id = v.fund_id
        WHERE f.slug = ? AND v.reporting_date = ?
        LIMIT 1
        """,
        (fund_slug, selected_date),
    ).fetchone()

    if filing is None:
        return None

    changes = position_changes(conn, fund_slug, selected_date)

    return FundDetail(
        fund_id=filing["fund_id"],
        slug=filing["slug"],
        name=filing["name"],
        reporting_date=filing["reporting_date"],
        filing_id=filing["filing_id"],
        accession_number=filing["accession_number"],
        filing_date=filing["filing_date"],
        form_type=filing["form_type"],
        report_type=filing["report_type"],
        filing_manager_name=filing["filing_manager_name"],
        form_13f_file_number=filing["form_13f_file_number"],
        sec_url=filing["sec_url"],
        top_positions=tuple(top),
        position_changes=tuple(changes),
    )
