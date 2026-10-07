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
        top.append(f"<tr><td>{i}</td><td><strong>{esc(p.issuer_name)}</strong><span class='subtle'>{esc(p.title_of_class or '')}</span></td><td>{money(p.value_dollars)}</td><td>{p.portfolio_weight*100:.1f}%</td><td>{shares}</td></tr>")
    changes=[]
    for c in detail.position_changes[:30]:
        changes.append(f"<tr><td><strong>{esc(c.issuer_name)}</strong></td><td><span class='status status-{esc(c.classification)}'>{esc(c.classification)}</span></td><td>{money(c.previous_value_dollars)}</td><td>{money(c.value_dollars)}</td><td>{signed_money(c.value_change_dollars)}</td><td>{signed_pct(c.value_change_percent)}</td><td>{signed_pct(c.shares_change_percent)}</td></tr>")
    sec=f'<a class="button" href="{esc(detail.sec_url)}" target="_blank" rel="noopener">View SEC filing ↗</a>' if detail.sec_url else ""
    body=f"""<main class="container"><section class="page-heading"><a class="back" href="../index.html">← All funds</a><div class="heading-row"><div><p class="eyebrow">Fund profile</p><h1>{esc(detail.name)}</h1><p class="subtitle">Latest 13F reporting period: {esc(detail.reporting_date)}</p></div>{sec}</div></section>
<section class="info-grid"><div class="info-card"><span>Filing date</span><strong>{esc(detail.filing_date)}</strong></div><div class="info-card"><span>Form</span><strong>{esc(detail.form_type)}</strong></div><div class="info-card"><span>Manager</span><strong>{esc(detail.filing_manager_name or "—")}</strong></div><div class="info-card"><span>13F file number</span><strong>{esc(detail.form_13f_file_number or "—")}</strong></div></section>
<section class="panel"><div class="section-heading"><div><p class="eyebrow">Portfolio</p><h2>Top 10 holdings</h2></div><span class="period">{esc(detail.reporting_date)}</span></div><div class="table-wrap"><table><thead><tr><th>#</th><th>Security</th><th>Value</th><th>Portfolio</th><th>Shares</th></tr></thead><tbody>{''.join(top)}</tbody></table></div></section>
<section class="panel"><div class="section-heading"><div><p class="eyebrow">Quarter over quarter</p><h2>Position changes</h2></div><span class="muted">Largest changes by reported value</span></div><div class="table-wrap"><table><thead><tr><th>Security</th><th>Change</th><th>Previous value</th><th>Current value</th><th>Value Δ</th><th>Value %</th><th>Shares %</th></tr></thead><tbody>{''.join(changes)}</tbody></table></div><p class="table-note">Showing the 30 largest changes. 13F data represents reportable long positions and does not show a manager's complete short book.</p></section></main>"""
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
<p class="as-of">Latest reporting period: <strong>{esc(latest or "—")}</strong></p></section>

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
<div class="toolbar"><span id="resultCount" class="muted"></span><label>Sort by <select id="sortBy"><option value="value">Total reported value</option><option value="funds">Number of funds</option><option value="name">Security name</option></select><button id="sortDirection" class="sort-button" type="button" aria-label="Toggle sort direction">↓</button></label></div>
<div class="table-wrap"><table id="overlapTable"><thead><tr><th>Security</th><th>Funds</th><th>Total reported value</th><th>Tracked funds</th></tr></thead><tbody></tbody></table></div>
<p id="emptyState" class="empty-state" hidden>No securities match the current filters.</p>
</section>
</main>
<script>
const securities = {payload};
const fundNames = {fund_name_data};
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
    else result = a.value - b.value;
    return descending ? -result : result;
  }});

  tableBody.innerHTML = filtered.slice(0, 500).map(item =>
    "<tr><td><strong>" + escapeHtml(item.issuer) + "</strong></td><td>" +
    item.funds.length + "</td><td>" + formatMoney(item.value) +
    "</td><td>" + item.funds.map(f => escapeHtml(fundNames[f] || f)).join(", ") + "</td></tr>"
  ).join("");
  resultCount.textContent = filtered.length.toLocaleString() +
    " securities match" + (filtered.length > 500 ? " (showing top 500)" : "");
  emptyState.hidden = filtered.length !== 0;
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

def generate(output=DEFAULT_OUTPUT):
    if output.exists():shutil.rmtree(output)
    (output/"fund").mkdir(parents=True);(output/"css").mkdir(parents=True)
    conn=connect()
    (output/"index.html").write_text(render_overview(conn),encoding="utf-8")
    (output/"13f-analysis.html").write_text(render_overlap(conn),encoding="utf-8")
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
