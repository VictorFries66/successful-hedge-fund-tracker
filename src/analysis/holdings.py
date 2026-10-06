"""Reusable 13F portfolio analysis queries."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Position:
    fund_id: int
    fund_name: str
    reporting_date: str
    filing_id: int
    issuer_name: str
    cusip: Optional[str]
    figi: Optional[str]
    title_of_class: Optional[str]
    put_call: Optional[str]
    value_dollars: int
    shares_or_principal: Optional[int]
    shares_or_principal_type: Optional[str]
    portfolio_weight: float


@dataclass(frozen=True)
class PositionChange:
    fund_id: int
    fund_name: str
    reporting_date: str
    previous_reporting_date: Optional[str]
    issuer_name: str
    cusip: Optional[str]
    previous_value_dollars: Optional[int]
    value_dollars: int
    value_change_dollars: Optional[int]
    value_change_percent: Optional[float]
    previous_shares: Optional[int]
    shares: Optional[int]
    shares_change: Optional[int]
    shares_change_percent: Optional[float]
    classification: str



def latest_positions(conn, fund_slug=None, reporting_date=None):
    """Return canonical latest-period positions, optionally filtered."""
    clauses = []
    params = []

    if fund_slug is not None:
        clauses.append("f.slug = ?")
        params.append(fund_slug)
    if reporting_date is not None:
        clauses.append("v.reporting_date = ?")
        params.append(reporting_date)
    else:
        clauses.append("""
            v.reporting_date = (
                SELECT MAX(v2.reporting_date)
                FROM latest_13f_by_period v2
                WHERE v2.fund_id = v.fund_id
            )
        """)

    where = "WHERE " + " AND ".join(clauses)

    rows = conn.execute(
        f"""
        WITH position_totals AS (
            SELECT
                h.filing_id,
                SUM(COALESCE(h.value_dollars, 0)) AS total_value
            FROM holdings_13f h
            GROUP BY h.filing_id
        )
        SELECT
            f.id AS fund_id,
            f.name AS fund_name,
            v.reporting_date,
            v.id AS filing_id,
            h.issuer_name,
            h.cusip,
            h.figi,
            h.title_of_class,
            h.put_call,
            COALESCE(h.value_dollars, 0) AS value_dollars,
            h.shares_or_principal,
            h.shares_or_principal_type,
            CASE
                WHEN pt.total_value > 0
                THEN CAST(COALESCE(h.value_dollars, 0) AS REAL) / pt.total_value
                ELSE 0
            END AS portfolio_weight
        FROM latest_13f_by_period v
        JOIN funds f ON f.id = v.fund_id
        JOIN holdings_13f h ON h.filing_id = v.id
        JOIN position_totals pt ON pt.filing_id = v.id
        {where}
        ORDER BY f.name, v.reporting_date DESC, value_dollars DESC, h.issuer_name
        """,
        params,
    ).fetchall()

    return [Position(**dict(row)) for row in rows]


def top_positions(conn, fund_slug, reporting_date=None, limit=10):
    """Return the largest positions for one fund and reporting period."""
    positions = latest_positions(conn, fund_slug, reporting_date)
    if not positions:
        return []
    if reporting_date is None:
        latest_date = positions[0].reporting_date
        positions = [p for p in positions if p.reporting_date == latest_date]
    return positions[:limit]


def _change_pct(previous, current):
    if previous in (None, 0) or current is None:
        return None
    return ((current - previous) / previous) * 100.0


def position_changes(conn, fund_slug, reporting_date=None):
    """Compare a fund's canonical quarter with its immediately prior quarter."""
    target = latest_positions(conn, fund_slug, reporting_date)
    if not target:
        return []

    current_date = target[0].reporting_date
    previous_row = conn.execute(
        """
        SELECT MAX(reporting_date) AS reporting_date
        FROM latest_13f_by_period v
        JOIN funds f ON f.id = v.fund_id
        WHERE f.slug = ? AND reporting_date < ?
        """,
        (fund_slug, current_date),
    ).fetchone()
    previous_date = previous_row["reporting_date"]

    if previous_date is None:
        return [
            PositionChange(
                fund_id=p.fund_id,
                fund_name=p.fund_name,
                reporting_date=p.reporting_date,
                previous_reporting_date=None,
                issuer_name=p.issuer_name,
                cusip=p.cusip,
                previous_value_dollars=None,
                value_dollars=p.value_dollars,
                value_change_dollars=None,
                value_change_percent=None,
                previous_shares=None,
                shares=p.shares_or_principal,
                shares_change=None,
                shares_change_percent=None,
                classification="new",
            )
            for p in target
        ]

    previous = latest_positions(conn, fund_slug, previous_date)
    previous_by_key = {
        (p.cusip or p.figi or f"{p.issuer_name}|{p.title_of_class or ''}"): p
        for p in previous
    }
    current_by_key = {
        (p.cusip or p.figi or f"{p.issuer_name}|{p.title_of_class or ''}"): p
        for p in target
    }

    results = []
    for key in sorted(set(previous_by_key) | set(current_by_key)):
        old = previous_by_key.get(key)
        new = current_by_key.get(key)

        if new is None:
            results.append(PositionChange(
                fund_id=old.fund_id,
                fund_name=old.fund_name,
                reporting_date=current_date,
                previous_reporting_date=previous_date,
                issuer_name=old.issuer_name,
                cusip=old.cusip,
                previous_value_dollars=old.value_dollars,
                value_dollars=0,
                value_change_dollars=-old.value_dollars,
                value_change_percent=-100.0,
                previous_shares=old.shares_or_principal,
                shares=0,
                shares_change=(
                    -old.shares_or_principal
                    if old.shares_or_principal is not None else None
                ),
                shares_change_percent=-100.0,
                classification="exited",
            ))
            continue

        if old is None:
            results.append(PositionChange(
                fund_id=new.fund_id,
                fund_name=new.fund_name,
                reporting_date=current_date,
                previous_reporting_date=previous_date,
                issuer_name=new.issuer_name,
                cusip=new.cusip,
                previous_value_dollars=None,
                value_dollars=new.value_dollars,
                value_change_dollars=None,
                value_change_percent=None,
                previous_shares=None,
                shares=new.shares_or_principal,
                shares_change=None,
                shares_change_percent=None,
                classification="new",
            ))
            continue

        old_shares = old.shares_or_principal
        new_shares = new.shares_or_principal
        if old_shares in (None, 0) and new_shares not in (None, 0):
            classification = "new"
        elif old_shares not in (None, 0) and new_shares in (None, 0):
            classification = "exited"
        elif old_shares is None or new_shares is None:
            classification = "unknown"
        elif new_shares > old_shares:
            classification = "increased"
        elif new_shares < old_shares:
            classification = "reduced"
        else:
            classification = "unchanged"

        results.append(PositionChange(
            fund_id=new.fund_id,
            fund_name=new.fund_name,
            reporting_date=current_date,
            previous_reporting_date=previous_date,
            issuer_name=new.issuer_name,
            cusip=new.cusip,
            previous_value_dollars=old.value_dollars,
            value_dollars=new.value_dollars,
            value_change_dollars=new.value_dollars - old.value_dollars,
            value_change_percent=_change_pct(old.value_dollars, new.value_dollars),
            previous_shares=old_shares,
            shares=new_shares,
            shares_change=(
                new_shares - old_shares
                if old_shares is not None and new_shares is not None
                else None
            ),
            shares_change_percent=_change_pct(old_shares, new_shares),
            classification=classification,
        ))

    return sorted(results, key=lambda x: abs(x.value_change_dollars or 0), reverse=True)
