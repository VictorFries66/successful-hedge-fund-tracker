"""Generate the static hedge-fund dashboard from the SQLite analysis layer."""

from __future__ import annotations

import argparse
import html
import shutil
from pathlib import Path

from src.analysis import fund_detail, fund_overview, portfolio_overlap
from src.database.database import connect

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "_site"

def esc(value):
    return html.escape("" if value is None else str(value))

def pct(value):
    return "—" if value is None else f"{value:.1f}%"

def money(value):
    if value is None:
        return "—"
    value = int(value)
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if abs(value) >= 1_000:
        return f"${value / 1_000:.0f}K"
    return f"${value:,}"

def signed_pct(value):
    return "—" if value is None else f"{value:+.1f}%"

def signed_money(value):
    if value is None:
        return "—"
    return f"{'-' if value < 0 else '+'}{money(abs(value))}"

def layout(title, body, active="", nested=False):
    nav = [("index.html","Hedge Funds","funds"),("13f-analysis.html","13F Analysis","13f"),("13d-analysis.html","13D Analysis","13d")]
    prefix = "../" if nested else ""
    css = "../css/style.css" if nested else "css/style.css"
    links = "".join(f'<a class="nav-link {"active" if active == key else ""}" href="{prefix}{href}">{label}</a>' for href,label,key in nav)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} · Successful Hedge Fund Investment Tracker</title><link rel="stylesheet" href="{css}"></head>
<body><header class="site-header"><div class="header-inner"><a class="brand" href="{prefix}index.html">Hedge Fund Investment Tracker</a><nav>{links}</nav></div></header>{body}</body></html>"""

def render_overview(conn):
    rows=fund_overview(conn)
    cards=[]
    for fund in rows:
        tags="".join(f'<span class="tag">{esc(tag)}</span>' for tag in fund.strategy_tags)
        cards.append(f"""<a class="fund-card" href="fund/{esc(fund.slug)}.html">
<div class="fund-card-top"><h3>{esc(fund.name)}</h3><span class="arrow">→</span></div>
<div class="fund-meta">Founded {fund.founded_year or "—"} · {fund.lifespan_years or "—"} years</div>
<div class="metrics"><div><span>Since inception</span><strong>{pct(fund.arr_since_inception)}</strong></div><div><span>5 year</span><strong>{pct(fund.arr_5_year)}</strong></div><div><span>3 year</span><strong>{pct(fund.arr_3_year)}</strong></div></div>
<div class="tags">{tags or '<span class="muted">No strategy tags</span>'}</div></a>""")
    latest=max((r.latest_reporting_date for r in rows if r.latest_reporting_date),default=None)
    return layout("Hedge Funds",f"""<main class="container"><section class="hero"><p class="eyebrow">8 tracked funds</p><h1>Successful Hedge Funds</h1><p>Track performance, SEC 13F portfolios, and where the investment strategies overlap.</p><p class="as-of">Latest 13F reporting period: <strong>{esc(latest or "—")}</strong></p></section><section class="fund-grid">{''.join(cards)}</section></main>""","funds")

def render_fund(conn,slug):
    detail=fund_detail(conn,slug)
    if detail is None:return None
    top=[]
    for i,p in enumerate(detail.top_positions,1):
        shares=f"{p.shares_or_principal:,} {esc(p.shares_or_principal_type or '')}" if p.shares_or_principal is not None else "—"
        top.append(f"<tr><td data-sort-value=\"{i}\">{i}</td><td data-sort-value=\"{esc(p.issuer_name)}\"><strong>{esc(p.issuer_name)}</strong><span class='subtle'>{esc(p.title_of_class or '')}</span></td><td data-sort-value=\"{p.value_dollars or 0}\">{money(p.value_dollars)}</td><td data-sort-value=\"{p.portfolio_weight * 100}\">{p.portfolio_weight*100:.1f}%</td><td data-sort-value=\"{p.shares_or_principal if p.shares_or_principal is not None else ''}\">{shares}</td></tr>")
    changes=[]
    for c in detail.position_changes[:30]:
        changes.append(f"<tr><td data-sort-value=\"{esc(c.issuer_name)}\"><strong>{esc(c.issuer_name)}</strong></td><td data-sort-value=\"{esc(c.classification)}\"><span class='status status-{esc(c.classification)}'>{esc(c.classification)}</span></td><td data-sort-value=\"{c.previous_value_dollars if c.previous_value_dollars is not None else ''}\">{money(c.previous_value_dollars)}</td><td data-sort-value=\"{c.value_dollars if c.value_dollars is not None else ''}\">{money(c.value_dollars)}</td><td data-sort-value=\"{c.value_change_dollars if c.value_change_dollars is not None else ''}\">{signed_money(c.value_change_dollars)}</td><td data-sort-value=\"{c.value_change_percent if c.value_change_percent is not None else ''}\">{signed_pct(c.value_change_percent)}</td><td data-sort-value=\"{c.shares_change_percent if c.shares_change_percent is not None else ''}\">{signed_pct(c.shares_change_percent)}</td></tr>")
    sec=f'<a class="button" href="{esc(detail.sec_url)}" target="_blank" rel="noopener">View SEC filing ↗</a>' if detail.sec_url else ""
    body=f"""<main class="container"><section class="page-heading"><a class="back" href="../index.html">← All funds</a><div class="heading-row"><div><p class="eyebrow">Fund profile</p><h1>{esc(detail.name)}</h1><p class="subtitle">Latest 13F reporting period: {esc(detail.reporting_date)}</p></div>{sec}</div></section>
<section class="info-grid"><div class="info-card"><span>Filing date</span><strong>{esc(detail.filing_date)}</strong></div><div class="info-card"><span>Form</span><strong>{esc(detail.form_type)}</strong></div><div class="info-card"><span>Manager</span><strong>{esc(detail.filing_manager_name or "—")}</strong></div><div class="info-card"><span>13F file number</span><strong>{esc(detail.form_13f_file_number or "—")}</strong></div></section>
<section class="panel"><div class="section-heading"><div><p class="eyebrow">Portfolio</p><h2>Top 10 holdings</h2></div><span class="period">{esc(detail.reporting_date)}</span></div><div class="table-wrap"><table class="sortable-table"><thead><tr><th data-sort-type="number"><button class="table-sort" type="button"># <span aria-hidden="true">↕</span></button></th><th data-sort-type="text"><button class="table-sort" type="button">Security <span aria-hidden="true">↕</span></button></th><th data-sort-type="number"><button class="table-sort" type="button">Value <span aria-hidden="true">↕</span></button></th><th data-sort-type="number"><button class="table-sort" type="button">Portfolio <span aria-hidden="true">↕</span></button></th><th data-sort-type="number"><button class="table-sort" type="button">Shares <span aria-hidden="true">↕</span></button></th></tr></thead><tbody>{''.join(top)}</tbody></table></div></section>
<section class="panel"><div class="section-heading"><div><p class="eyebrow">Quarter over quarter</p><h2>Position changes</h2></div><span class="muted">Largest changes by reported value</span></div><div class="table-wrap"><table class="sortable-table"><thead><tr><th data-sort-type="text"><button class="table-sort" type="button">Security <span aria-hidden="true">↕</span></button></th><th data-sort-type="text"><button class="table-sort" type="button">Change <span aria-hidden="true">↕</span></button></th><th data-sort-type="number"><button class="table-sort" type="button">Previous value <span aria-hidden="true">↕</span></button></th><th data-sort-type="number"><button class="table-sort" type="button">Current value <span aria-hidden="true">↕</span></button></th><th data-sort-type="number"><button class="table-sort" type="button">Value Δ <span aria-hidden="true">↕</span></button></th><th data-sort-type="number"><button class="table-sort" type="button">Value % <span aria-hidden="true">↕</span></button></th><th data-sort-type="number"><button class="table-sort" type="button">Shares % <span aria-hidden="true">↕</span></button></th></tr></thead><tbody>{''.join(changes)}</tbody></table></div><p class="table-note">Showing the 30 largest changes. 13F data represents reportable long positions and does not show a manager's complete short book.</p></section></main>
<script>
document.querySelectorAll("table.sortable-table").forEach(table => {{
  table.querySelectorAll("thead th").forEach((header, columnIndex) => {{
    const button = header.querySelector("button");
    if (!button) return;
    button.addEventListener("click", () => {{
      const sameColumn = table.dataset.sortColumn === String(columnIndex);
      const descending = sameColumn ? table.dataset.sortDirection !== "desc" : true;
      table.dataset.sortColumn = String(columnIndex);
      table.dataset.sortDirection = descending ? "desc" : "asc";
      const type = header.dataset.sortType || "text";
      const rows = Array.from(table.tBodies[0].rows);
      rows.sort((a, b) => {{
        const av = a.cells[columnIndex].dataset.sortValue ?? a.cells[columnIndex].textContent.trim();
        const bv = b.cells[columnIndex].dataset.sortValue ?? b.cells[columnIndex].textContent.trim();
        let result;
        if (type === "number") {{
          const an = av === "" ? Number.NEGATIVE_INFINITY : Number(av);
          const bn = bv === "" ? Number.NEGATIVE_INFINITY : Number(bv);
          result = an - bn;
        }} else {{
          result = av.localeCompare(bv, undefined, {{sensitivity: "base"}});
        }}
        return descending ? -result : result;
      }});
      rows.forEach(row => table.tBodies[0].appendChild(row));
      table.querySelectorAll("thead th").forEach((th, index) => {{
        th.setAttribute("aria-sort", index === columnIndex ? (descending ? "descending" : "ascending") : "none");
        const indicator = th.querySelector("button span");
        if (indicator) indicator.textContent = index === columnIndex ? (descending ? "↓" : "↑") : "↕";
      }});
    }});
  }});
}});
</script>"""
    return layout(detail.name,body,"funds",nested=True)

def render_overlap(conn):
    overlaps = portfolio_overlap(conn, min_funds=1)
    latest_dates = conn.execute(
        "SELECT DISTINCT reporting_date FROM latest_13f_by_period ORDER BY reporting_date DESC"
    ).fetchall()
    latest = latest_dates[0]["reporting_date"] if latest_dates else None

    funds = conn.execute(
        "SELECT slug, name FROM funds WHERE active=1 ORDER BY name"
    ).fetchall()
    tag_rows = conn.execute(
        """
        SELECT f.slug AS fund_slug, st.slug AS tag_slug
        FROM funds f
        JOIN fund_strategy_tags fst ON fst.fund_id = f.id
        JOIN strategy_tags st ON st.id = fst.tag_id
        WHERE f.active = 1
        """
    ).fetchall()
    fund_tags = {}
    for row in tag_rows:
        fund_tags.setdefault(row["fund_slug"], []).append(row["tag_slug"])

    tag_names = dict(
        conn.execute("SELECT slug, name FROM strategy_tags ORDER BY name").fetchall()
    )

    # Quarter-over-quarter share changes by security and fund. Principal amounts
    # are deliberately excluded because they are not share quantities.
    share_change_rows = conn.execute(
        """
        WITH latest AS (
            SELECT v.fund_id, v.id AS filing_id, v.reporting_date
            FROM latest_13f_by_period v
            WHERE v.reporting_date = (
                SELECT MAX(v2.reporting_date) FROM latest_13f_by_period v2
                WHERE v2.fund_id = v.fund_id
            )
        ),
        prior AS (
            SELECT l.fund_id, MAX(v.reporting_date) AS reporting_date
            FROM latest l JOIN latest_13f_by_period v
              ON v.fund_id = l.fund_id AND v.reporting_date < l.reporting_date
            GROUP BY l.fund_id
        ),
        current_positions AS (
            SELECT l.fund_id,
                   COALESCE(NULLIF(h.cusip, ''), NULLIF(h.figi, ''),
                       UPPER(TRIM(h.issuer_name)) || '|' ||
                       COALESCE(UPPER(TRIM(h.title_of_class)), '')) AS position_key,
                   SUM(CASE WHEN UPPER(COALESCE(h.shares_or_principal_type, '')) IN ('SH', 'SHARES')
                            THEN h.shares_or_principal END) AS shares
            FROM latest l JOIN holdings_13f h ON h.filing_id = l.filing_id
            GROUP BY l.fund_id, position_key
        ),
        previous_positions AS (
            SELECT p.fund_id,
                   COALESCE(NULLIF(h.cusip, ''), NULLIF(h.figi, ''),
                       UPPER(TRIM(h.issuer_name)) || '|' ||
                       COALESCE(UPPER(TRIM(h.title_of_class)), '')) AS position_key,
                   SUM(CASE WHEN UPPER(COALESCE(h.shares_or_principal_type, '')) IN ('SH', 'SHARES')
                            THEN h.shares_or_principal END) AS shares
            FROM prior p
            JOIN latest_13f_by_period v
              ON v.fund_id = p.fund_id AND v.reporting_date = p.reporting_date
            JOIN holdings_13f h ON h.filing_id = v.id
            GROUP BY p.fund_id, position_key
        ),
        position_keys AS (
            SELECT fund_id, position_key FROM current_positions
            UNION SELECT fund_id, position_key FROM previous_positions
        )
        SELECT f.slug AS fund_slug, k.position_key,
               cur.shares AS current_shares, prev.shares AS previous_shares
        FROM position_keys k JOIN funds f ON f.id = k.fund_id
        LEFT JOIN current_positions cur
          ON cur.fund_id = k.fund_id AND cur.position_key = k.position_key
        LEFT JOIN previous_positions prev
          ON prev.fund_id = k.fund_id AND prev.position_key = k.position_key
        WHERE f.active = 1
        """
    ).fetchall()
    share_changes_by_key = {}
    for row in share_change_rows:
        current_shares = row["current_shares"]
        previous_shares = row["previous_shares"]
        if current_shares is None or previous_shares is None:
            continue
        share_changes_by_key.setdefault(row["position_key"], {})[row["fund_slug"]] = (
            int(current_shares) - int(previous_shares)
        )

    data = []
    for item in overlaps:
        tags = sorted(
            {tag for fund in item.fund_slugs for tag in fund_tags.get(fund, [])}
        )
        data.append(
            {
                "issuer": item.issuer_name,
                "funds": list(item.fund_slugs),
                "tags": tags,
                "value": item.total_value_dollars,
                "position_key": item.position_key,
                "share_changes": share_changes_by_key.get(item.position_key, {}),
            }
        )

    fund_controls = "".join(
        f'<label class="filter-chip"><input type="checkbox" class="fund-filter" value="{esc(row["slug"])}"><span>{esc(row["name"])}</span></label>'
        for row in funds
    )
    tag_controls = "".join(
        f'<label class="filter-chip"><input type="checkbox" class="tag-filter" value="{esc(slug)}"><span>{esc(name)}</span></label>'
        for slug, name in tag_names.items()
    )

    import json
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    fund_name_data = json.dumps(
        {row["slug"]: row["name"] for row in funds}, separators=(",", ":")
    )

    body = f"""<main class="container">
<section class="hero compact"><p class="eyebrow">Cross-fund analysis</p><h1>13F Portfolio Explorer</h1>
<p>Filter and sort the latest reportable long positions across the eight tracked funds.</p>
<p class="as-of">Latest reporting period: <strong>{esc(latest or "—")}</strong></p>
<p><a class="guide-link" href="13f-guide.html">How 13F filings work <span aria-hidden="true">→</span></a></p></section>

<section class="panel filter-panel">
<div class="section-heading"><div><p class="eyebrow">Filters</p><h2>Build your portfolio group</h2></div><button id="clearFilters" class="text-button" type="button">Clear all</button></div>
<div class="filter-section"><span class="filter-label">Strategy tags</span><div class="filter-chips">{tag_controls}</div></div>
<div class="filter-section"><span class="filter-label">Funds</span><div class="filter-chips">{fund_controls}</div></div>
<div class="filter-row">
<label>Fund match <select id="fundMode"><option value="any">Any selected fund</option><option value="all">All selected funds</option><option value="exact">Exactly these funds</option></select></label>
<label>Minimum funds <input id="minFunds" type="number" min="1" max="8" value="1"></label>
<label>Min reported value <input id="minValue" type="number" min="0" step="1000000" placeholder="$0"></label>
<label>Max reported value <input id="maxValue" type="number" min="0" step="1000000" placeholder="No limit"></label>
</div>
</section>

<section class="panel">
<div class="toolbar"><span id="resultCount" class="muted"></span><label>Sort by <select id="sortBy"><option value="value">Total reported value</option><option value="shares">Net share change</option><option value="funds">Number of funds</option><option value="name">Security name</option></select><button id="sortDirection" class="sort-button" type="button" aria-label="Toggle sort direction">↓</button></label></div>
<div class="table-wrap"><table id="overlapTable"><thead><tr><th>Security</th><th>Funds</th><th>Total reported value</th><th>Net share change</th><th>Tracked funds</th></tr></thead><tbody></tbody></table></div>
<p class="table-note">Net share change sums comparable quarter-over-quarter share-count changes for funds selected by your filters. Principal-amount positions and positions without comparable share data are excluded. This measures reported holdings changes, not trade volume.</p>
<p id="emptyState" class="empty-state" hidden>No securities match the current filters.</p>
</section>
</main>
<script>
const securities = {payload};
const fundNames = {fund_name_data};
const fundTags = {json.dumps(fund_tags, separators=(",", ":"))};
const tableBody = document.querySelector("#overlapTable tbody");
const resultCount = document.getElementById("resultCount");
const emptyState = document.getElementById("emptyState");
const sortBy = document.getElementById("sortBy");
const sortDirection = document.getElementById("sortDirection");
let descending = true;

function selected(selector) {{
  return [...document.querySelectorAll(selector)].filter(x => x.checked).map(x => x.value);
}}

function matchesFunds(item, selectedFunds, mode) {{
  if (!selectedFunds.length) return true;
  const held = new Set(item.funds);
  if (mode === "all") return selectedFunds.every(f => held.has(f));
  if (mode === "exact") return held.size === selectedFunds.length && selectedFunds.every(f => held.has(f));
  return selectedFunds.some(f => held.has(f));
}}

function render() {{
  const tags = selected(".tag-filter");
  const funds = selected(".fund-filter");
  const mode = document.getElementById("fundMode").value;
  const minFunds = Number(document.getElementById("minFunds").value || 1);
  const minValue = Number(document.getElementById("minValue").value || 0);
  const maxRaw = document.getElementById("maxValue").value;
  const maxValue = maxRaw === "" ? Infinity : Number(maxRaw);
  const sort = sortBy.value;

  let filtered = securities.filter(item => {{
    const tagMatch = !tags.length || tags.some(tag => item.tags.includes(tag));
    const fundMatch = matchesFunds(item, funds, mode);
    return tagMatch && fundMatch && item.funds.length >= minFunds &&
      item.value >= minValue && item.value <= maxValue;
  }});

  filtered.sort((a, b) => {{
    let result;
    if (sort === "name") result = a.issuer.localeCompare(b.issuer);
    else if (sort === "funds") result = a.funds.length - b.funds.length;
    else if (sort === "shares") result = (netShareChange(a, funds, tags) ?? Number.NEGATIVE_INFINITY) - (netShareChange(b, funds, tags) ?? Number.NEGATIVE_INFINITY);
    else result = a.value - b.value;
    return descending ? -result : result;
  }});

  tableBody.innerHTML = filtered.slice(0, 500).map(item => {
    const shareChange = netShareChange(item, funds, tags);
    const shareText = shareChange === null ? "—" :
      (shareChange > 0 ? "+" : "") + shareChange.toLocaleString() + " shares";
    return "<tr><td><strong>" + escapeHtml(item.issuer) + "</strong></td><td>" +
      item.funds.length + "</td><td>" + formatMoney(item.value) +
      "</td><td>" + shareText + "</td><td>" +
      item.funds.map(f => escapeHtml(fundNames[f] || f)).join(", ") + "</td></tr>";
  }).join("");
  resultCount.textContent = filtered.length.toLocaleString() +
    " securities match" + (filtered.length > 500 ? " (showing top 500)" : "");
  emptyState.hidden = filtered.length !== 0;
}}

function netShareChange(item, selectedFunds, selectedTags) {{
  let eligibleFunds = Object.keys(item.share_changes || {{}});
  if (selectedFunds.length) {{
    eligibleFunds = eligibleFunds.filter(f => selectedFunds.includes(f));
  }}
  if (selectedTags.length) {{
    eligibleFunds = eligibleFunds.filter(f =>
      (fundTags[f] || []).some(tag => selectedTags.includes(tag))
    );
  }}
  if (!eligibleFunds.length) return null;
  return eligibleFunds.reduce((total, fund) => total + item.share_changes[fund], 0);
}}

function escapeHtml(value) {{
  const div = document.createElement("div");
  div.textContent = value;
  return div.innerHTML;
}}

function formatMoney(value) {{
  if (Math.abs(value) >= 1e9) return "$" + (value / 1e9).toFixed(1) + "B";
  if (Math.abs(value) >= 1e6) return "$" + (value / 1e6).toFixed(1) + "M";
  if (Math.abs(value) >= 1e3) return "$" + Math.round(value / 1e3) + "K";
  return "$" + value.toLocaleString();
}}

document.querySelectorAll(".tag-filter,.fund-filter,#fundMode,#minFunds,#minValue,#maxValue").forEach(el => {{
  el.addEventListener("input", render);
  el.addEventListener("change", render);
}});
sortBy.addEventListener("change", render);
sortDirection.addEventListener("click", () => {{
  descending = !descending;
  sortDirection.textContent = descending ? "↓" : "↑";
  render();
}});
document.getElementById("clearFilters").addEventListener("click", () => {{
  document.querySelectorAll(".tag-filter,.fund-filter").forEach(el => el.checked = false);
  document.getElementById("fundMode").value = "any";
  document.getElementById("minFunds").value = "1";
  document.getElementById("minValue").value = "";
  document.getElementById("maxValue").value = "";
  render();
}});
render();
</script>"""
    return layout("13F Analysis", body, "13f")

def render_13f_guide():
    body = """<main class="container">
<section class="page-heading"><a class="back" href="13f-analysis.html">← Back to 13F Portfolio Explorer</a>
<p class="eyebrow">A quick guide</p><h1>How 13F filings work</h1>
<p class="subtitle">What these reports tell you, when they are published, and how to interpret them.</p></section>

<section class="panel guide-panel"><p class="eyebrow">The basics</p><h2>What is a Form 13F?</h2>
<p>Form 13F is a quarterly disclosure filed with the U.S. Securities and Exchange Commission (SEC) by certain institutional investment managers. In general, a manager is required to file if it exercises investment discretion over at least $100 million in securities on the SEC's official Section 13(f) securities list, measured on the last trading day of any month in a calendar year.</p>
<p>It is a disclosure of specified reportable securities—not a complete statement of everything a hedge fund owns or every trade it makes.</p></section>

<section class="panel guide-panel"><p class="eyebrow">The calendar</p><h2>Which time period does a filing cover?</h2>
<p>Each report is a snapshot of reportable holdings at the end of a calendar quarter:</p>
<ul><li><strong>March 31</strong> — first quarter</li><li><strong>June 30</strong> — second quarter</li><li><strong>September 30</strong> — third quarter</li><li><strong>December 31</strong> — fourth quarter</li></ul>
<p>Managers generally have <strong>45 days after quarter-end</strong> to submit the report. That means the information is already several weeks old when it becomes public. For example, a September 30 portfolio is generally due by mid-November.</p>
<p><strong>Important:</strong> the reporting date and filing date are different. The reporting date tells you when the portfolio was measured; the filing date tells you when the disclosure was submitted.</p></section>

<section class="panel guide-panel"><p class="eyebrow">What is disclosed</p><h2>What does a 13F show?</h2>
<p>For securities on the SEC's official Section 13(f) list, the information table generally identifies the issuer and security class and reports the number of shares (or principal amount, where applicable) and the reported fair market value as of quarter-end. The list mainly covers certain U.S.-traded stocks and ETFs, and also includes some other securities such as certain options and warrants.</p>
<ul><li>Which reportable securities the manager reported.</li><li>The reported share or principal amount.</li><li>The reported market value at the end of the quarter.</li><li>Whether a reported position appears, increases, decreases, or disappears compared with another quarter's filing.</li></ul></section>

<section class="panel guide-panel"><p class="eyebrow">What is not disclosed</p><h2>What does a 13F leave out?</h2>
<ul><li><strong>Short positions:</strong> managers do not report their short equity positions on Form 13F.</li>
<li><strong>Written options:</strong> short/written put and call options are not reported.</li>
<li><strong>Many other assets:</strong> assets that are not on the official Section 13(f) list—including cash and many other instruments—are outside the report.</li>
<li><strong>Live activity:</strong> the filing does not provide a running transaction history, exact trade dates, or the manager's reasoning.</li>
<li><strong>Some temporarily withheld positions:</strong> the SEC may grant confidential treatment in limited circumstances, so a public filing may not show every position immediately.</li></ul>
<p>As a result, a 13F should not be treated as the manager's complete portfolio, net exposure, or current positions.</p></section>

<section class="panel guide-panel"><p class="eyebrow">Reading the tracker</p><h2>How to interpret the tables here</h2>
<ul><li><strong>Top 10 holdings</strong> ranks the largest reported positions by their disclosed value in that filing.</li>
<li><strong>Position changes</strong> compares two reporting periods. A change in reported dollar value can come from a change in the number of shares, a change in the security's market price, or both.</li>
<li><strong>New / increased / reduced / exited</strong> describes the change visible between the filings—not necessarily a trade made at the quarter-end price or a complete change in the manager's exposure.</li></ul>
<p>Use the filing as a delayed clue about where a manager had reportable long exposure, not as a real-time instruction to copy a trade.</p></section>

<section class="guide-source"><p>For the official rules and detailed definitions, see the SEC's <a href="https://www.sec.gov/rules-regulations/staff-guidance/frequently-asked-questions-about-form-13f" target="_blank" rel="noopener">Frequently Asked Questions About Form 13F ↗</a> and the <a href="https://www.sec.gov/about/forms/form13f.pdf" target="_blank" rel="noopener">Form 13F and its instructions ↗</a>.</p></section>
</main>"""
    return layout("How 13F Filings Work", body, "13f")

def generate(output=DEFAULT_OUTPUT):
    if output.exists():shutil.rmtree(output)
    (output/"fund").mkdir(parents=True);(output/"css").mkdir(parents=True)
    conn=connect()
    (output/"index.html").write_text(render_overview(conn),encoding="utf-8")
    (output/"13f-analysis.html").write_text(render_overlap(conn),encoding="utf-8")
    (output/"13f-guide.html").write_text(render_13f_guide(),encoding="utf-8")
    (output/"13d-analysis.html").write_text(layout("13D Analysis",'<main class="container"><section class="hero"><p class="eyebrow">Coming next</p><h1>13D Analysis</h1><p>The 13D layer will be added after the 13F dashboard is complete.</p></section></main>',"13d"),encoding="utf-8")
    for row in conn.execute("SELECT slug FROM funds WHERE active=1 ORDER BY name"):
        page=render_fund(conn,row["slug"])
        if page:(output/"fund"/f'{row["slug"]}.html').write_text(page,encoding="utf-8")
    css=(ROOT/"website"/"css"/"style.css").read_text(encoding="utf-8")
    (output/"css"/"style.css").write_text(css,encoding="utf-8")
    conn.close();return output

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,default=DEFAULT_OUTPUT);args=parser.parse_args()
    print(f"Generated static dashboard at {generate(args.output)}")
