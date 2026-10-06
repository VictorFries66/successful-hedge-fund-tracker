"""Cross-fund 13F portfolio overlap analysis."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Overlap:
    issuer_name: str
    cusip: str | None
    fund_slugs: tuple[str, ...]
    fund_count: int
    total_value_dollars: int


def portfolio_overlap(conn, reporting_date=None, min_funds=2):
    """Find securities held by at least min_funds.

    If reporting_date is omitted, each fund's latest available reporting
    period is used. For a same-quarter comparison, pass a reporting date.
    """
    if reporting_date is None:
        date_clause = """
            v.reporting_date = (
                SELECT MAX(v2.reporting_date)
                FROM latest_13f_by_period v2
                WHERE v2.fund_id = v.fund_id
            )
        """
        params = [min_funds]
    else:
        date_clause = "v.reporting_date = ?"
        params = [reporting_date, min_funds]

    rows = conn.execute(
        f"""
        WITH positions AS (
            SELECT
                f.slug AS fund_slug,
                h.issuer_name,
                h.cusip,
                COALESCE(h.value_dollars, 0) AS value_dollars,
                COALESCE(
                    NULLIF(h.cusip, ''),
                    NULLIF(h.figi, ''),
                    UPPER(TRIM(h.issuer_name)) || '|' ||
                    COALESCE(UPPER(TRIM(h.title_of_class)), '')
                ) AS position_key
            FROM latest_13f_by_period v
            JOIN funds f ON f.id = v.fund_id
            JOIN holdings_13f h ON h.filing_id = v.id
            WHERE {date_clause}
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
            HAVING COUNT(DISTINCT fund_slug) >= ?
        )
        SELECT
            g.position_key,
            g.issuer_name,
            g.cusip,
            g.fund_count,
            g.total_value_dollars,
            p.fund_slug
        FROM grouped g
        JOIN positions p ON p.position_key = g.position_key
        ORDER BY g.fund_count DESC, g.total_value_dollars DESC, g.issuer_name, p.fund_slug
        """,
        params,
    ).fetchall()

    grouped = {}
    for row in rows:
        item = grouped.setdefault(
            row["position_key"],
            {
                "issuer_name": row["issuer_name"],
                "cusip": row["cusip"],
                "fund_count": row["fund_count"],
                "total_value_dollars": row["total_value_dollars"],
                "fund_slugs": [],
            },
        )
        if row["fund_slug"] not in item["fund_slugs"]:
            item["fund_slugs"].append(row["fund_slug"])

    return [
        Overlap(
            issuer_name=item["issuer_name"],
            cusip=item["cusip"],
            fund_slugs=tuple(item["fund_slugs"]),
            fund_count=item["fund_count"],
            total_value_dollars=item["total_value_dollars"],
        )
        for item in grouped.values()
    ]
