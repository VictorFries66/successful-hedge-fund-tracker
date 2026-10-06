"""Cross-fund 13F portfolio overlap analysis."""

from dataclasses import dataclass
from itertools import combinations


@dataclass(frozen=True)
class Overlap:
    issuer_name: str
    cusip: str | None
    fund_slugs: tuple[str, ...]
    fund_count: int
    total_value_dollars: int


def portfolio_overlap(conn, reporting_date=None, min_funds=2):
    """Find securities held by at least min_funds in the selected period.

    If reporting_date is omitted, each fund's latest available reporting
    period is used. For a true same-quarter comparison, pass a date.
    """
    if reporting_date is None:
        date_cte = """
            SELECT fund_id, MAX(reporting_date) AS reporting_date
            FROM latest_13f_by_period
            GROUP BY fund_id
        """
        join = "JOIN date_cte d ON d.fund_id = v.fund_id AND d.reporting_date = v.reporting_date"
        params = []
    else:
        date_cte = ""
        join = "AND v.reporting_date = ?"
        params = [reporting_date]

    rows = conn.execute(
        f"""
        WITH {date_cte}
        positions AS (
            SELECT
                f.slug AS fund_slug,
                f.name AS fund_name,
                h.issuer_name,
                h.cusip,
                h.figi,
                h.title_of_class,
                COALESCE(h.value_dollars, 0) AS value_dollars,
                COALESCE(
                    NULLIF(h.cusip, ''),
                    NULLIF(h.figi, ''),
                    UPPER(TRIM(h.issuer_name)) || '|' ||
                    COALESCE(UPPER(TRIM(h.title_of_class)), '')
                ) AS position_key
            FROM latest_13f_by_period v
            JOIN funds f ON f.id = v.fund_id
            {join}
            JOIN holdings_13f h ON h.filing_id = v.id
        ),
        grouped AS (
            SELECT
                position_key,
                MAX(issuer_name) AS issuer_name,
                MAX(cusip) AS cusip,
                COUNT(DISTINCT fund_slug) AS fund_count,
                SUM(value_dollars) AS total_value_dollars
            FROM positions
            GROUP BY position_key
        )
        SELECT
            g.issuer_name,
            g.cusip,
            g.fund_count,
            g.total_value_dollars
        FROM grouped g
        WHERE g.fund_count >= ?
        ORDER BY g.fund_count DESC, g.total_value_dollars DESC, g.issuer_name
        """,
        [*params, min_funds],
    ).fetchall()

    result = []
    for row in rows:
        funds = conn.execute(
            """
            SELECT DISTINCT f.slug
            FROM latest_13f_by_period v
            JOIN funds f ON f.id = v.fund_id
            JOIN holdings_13f h ON h.filing_id = v.id
            WHERE COALESCE(
                NULLIF(h.cusip, ''),
                NULLIF(h.figi, ''),
                UPPER(TRIM(h.issuer_name)) || '|' ||
                COALESCE(UPPER(TRIM(h.title_of_class)), '')
            ) = ?
            """
            + (" AND v.reporting_date = ?" if reporting_date else ""),
            [row["issuer_name"] if False else (
                row["cusip"] or row["issuer_name"]
            ), *([reporting_date] if reporting_date else [])],
        ).fetchall()

        # The lookup above is intentionally replaced below with a direct
        # key query so issuer-only fallbacks remain unambiguous.
        key = None
        if row["cusip"]:
            key = row["cusip"]
        else:
            key_row = conn.execute(
                """
                SELECT COALESCE(
                    NULLIF(h.cusip, ''),
                    NULLIF(h.figi, ''),
                    UPPER(TRIM(h.issuer_name)) || '|' ||
                    COALESCE(UPPER(TRIM(h.title_of_class)), '')
                ) AS position_key
                FROM latest_13f_by_period v
                JOIN holdings_13f h ON h.filing_id = v.id
                WHERE h.issuer_name = ?
                LIMIT 1
                """,
                (row["issuer_name"],),
            ).fetchone()
            key = key_row["position_key"] if key_row else None

        if key is None:
            continue

        funds = conn.execute(
            """
            SELECT DISTINCT f.slug
            FROM latest_13f_by_period v
            JOIN funds f ON f.id = v.fund_id
            JOIN holdings_13f h ON h.filing_id = v.id
            WHERE COALESCE(
                NULLIF(h.cusip, ''),
                NULLIF(h.figi, ''),
                UPPER(TRIM(h.issuer_name)) || '|' ||
                COALESCE(UPPER(TRIM(h.title_of_class)), '')
            ) = ?
            """
            + (" AND v.reporting_date = ?" if reporting_date else ""),
            [key, *([reporting_date] if reporting_date else [])],
        ).fetchall()

        result.append(Overlap(
            issuer_name=row["issuer_name"],
            cusip=row["cusip"],
            fund_slugs=tuple(r["slug"] for r in funds),
            fund_count=row["fund_count"],
            total_value_dollars=row["total_value_dollars"],
        ))

    return result
