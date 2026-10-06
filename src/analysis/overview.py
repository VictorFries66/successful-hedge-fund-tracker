"""Analysis contract for the fund overview page."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class FundOverview:
    fund_id: int
    slug: str
    name: str
    founded_year: Optional[int]
    lifespan_years: Optional[int]
    strategy_tags: tuple[str, ...]
    arr_since_inception: Optional[float]
    arr_5_year: Optional[float]
    arr_3_year: Optional[float]
    performance_as_of: Optional[str]
    latest_reporting_date: Optional[str]
    latest_filing_id: Optional[int]
    latest_holding_count: int
    latest_portfolio_value_dollars: int


def fund_overview(conn, as_of_year: Optional[int] = None) -> list[FundOverview]:
    """Return one overview record for every active tracked fund.

    Performance values come from fund_performance and are returned as stored.
    Lifespan is the number of years from founded_year through as_of_year.
    If as_of_year is omitted, the latest reporting year in the 13F data is used.
    """
    latest_year_row = conn.execute(
        "SELECT MAX(CAST(reporting_date AS INTEGER)) AS year "
        "FROM latest_13f_by_period"
    ).fetchone()
    effective_year = as_of_year
    if effective_year is None:
        effective_year = latest_year_row["year"] if latest_year_row["year"] is not None else None

    rows = conn.execute(
        """
        WITH latest AS (
            SELECT
                v.fund_id,
                v.reporting_date,
                v.id AS filing_id
            FROM latest_13f_by_period v
            WHERE v.reporting_date = (
                SELECT MAX(v2.reporting_date)
                FROM latest_13f_by_period v2
                WHERE v2.fund_id = v.fund_id
            )
        ),
        holding_totals AS (
            SELECT
                h.filing_id,
                COUNT(*) AS holding_count,
                SUM(COALESCE(h.value_dollars, 0)) AS portfolio_value_dollars
            FROM holdings_13f h
            GROUP BY h.filing_id
        ),
        performance AS (
            SELECT
                fund_id,
                MAX(CASE WHEN period_type = 'since_inception' THEN return_rate END)
                    AS arr_since_inception,
                MAX(CASE WHEN period_type = '5_year' THEN return_rate END)
                    AS arr_5_year,
                MAX(CASE WHEN period_type = '3_year' THEN return_rate END)
                    AS arr_3_year,
                MAX(as_of_date) AS performance_as_of
            FROM fund_performance
            GROUP BY fund_id
        )
        SELECT
            f.id AS fund_id,
            f.slug,
            f.name,
            f.founded_year,
            l.reporting_date AS latest_reporting_date,
            l.filing_id AS latest_filing_id,
            COALESCE(ht.holding_count, 0) AS latest_holding_count,
            COALESCE(ht.portfolio_value_dollars, 0) AS latest_portfolio_value_dollars,
            p.arr_since_inception,
            p.arr_5_year,
            p.arr_3_year,
            p.performance_as_of
        FROM funds f
        LEFT JOIN latest l ON l.fund_id = f.id
        LEFT JOIN holding_totals ht ON ht.filing_id = l.filing_id
        LEFT JOIN performance p ON p.fund_id = f.id
        WHERE f.active = 1
        ORDER BY f.name
        """
    ).fetchall()

    tags = {}
    for row in conn.execute(
        """
        SELECT f.id AS fund_id, st.name
        FROM funds f
        JOIN fund_strategy_tags fst ON fst.fund_id = f.id
        JOIN strategy_tags st ON st.id = fst.tag_id
        WHERE f.active = 1
        ORDER BY st.name
        """
    ).fetchall():
        tags.setdefault(row["fund_id"], []).append(row["name"])

    result = []
    for row in rows:
        founded_year = row["founded_year"]
        lifespan = (
            effective_year - founded_year
            if effective_year is not None and founded_year is not None
            else None
        )
        result.append(
            FundOverview(
                fund_id=row["fund_id"],
                slug=row["slug"],
                name=row["name"],
                founded_year=founded_year,
                lifespan_years=lifespan,
                strategy_tags=tuple(tags.get(row["fund_id"], [])),
                arr_since_inception=row["arr_since_inception"],
                arr_5_year=row["arr_5_year"],
                arr_3_year=row["arr_3_year"],
                performance_as_of=row["performance_as_of"],
                latest_reporting_date=row["latest_reporting_date"],
                latest_filing_id=row["latest_filing_id"],
                latest_holding_count=row["latest_holding_count"],
                latest_portfolio_value_dollars=row["latest_portfolio_value_dollars"],
            )
        )

    return result
