from src.database.database import connect, initialize_database
from src.sec.funds import SEC_ENTITIES

FUNDS = [
    ("citadel", "Citadel", 1990),
    ("de-shaw", "D.E. Shaw", 1988),
    ("millennium", "Millennium", 1989),
    ("tci", "TCI", 2003),
    ("pershing-square", "Pershing Square", 2003),
    ("elliott", "Elliott", 1977),
    ("aqr", "AQR", 1998),
    ("lone-pine", "Lone Pine", 1997),
]

STRATEGY_TAGS = {
    "multi-market-trader": "Multi-Market Trader",
    "quantitative": "Quantitative",
    "data-and-research": "Data and Research",
    "specialized-trading-teams": "Specialized Trading Teams",
    "long-term": "Long Term",
    "activist-investing": "Activist Investing",
    "event-driven": "Event Driven",
    "systematic": "Systematic",
    "stock-picker": "Stock Picker",
    "deep-research": "Deep Research",
}

FUND_TAGS = {
    "citadel": ["multi-market-trader", "quantitative"],
    "de-shaw": ["data-and-research", "quantitative"],
    "millennium": ["specialized-trading-teams"],
    "tci": ["long-term", "activist-investing"],
    "pershing-square": ["activist-investing"],
    "elliott": ["activist-investing", "event-driven"],
    "aqr": ["systematic", "quantitative"],
    "lone-pine": ["stock-picker", "deep-research"],
}

def seed():
    initialize_database()
    with connect() as conn:
        conn.executemany('''
            INSERT INTO funds (slug, name, founded_year)
            VALUES (?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
              name=excluded.name, founded_year=excluded.founded_year
        ''', FUNDS)

        conn.executemany(
            '''INSERT INTO strategy_tags (slug, name)
               VALUES (?, ?)
               ON CONFLICT(slug) DO UPDATE SET name=excluded.name''',
            list(STRATEGY_TAGS.items())
        )

        for fund_slug, tag_slugs in FUND_TAGS.items():
            fund_id = conn.execute(
                "SELECT id FROM funds WHERE slug = ?", (fund_slug,)
            ).fetchone()[0]
            for tag_slug in tag_slugs:
                tag_id = conn.execute(
                    "SELECT id FROM strategy_tags WHERE slug = ?", (tag_slug,)
                ).fetchone()[0]
                conn.execute(
                    "INSERT OR IGNORE INTO fund_strategy_tags (fund_id, tag_id) VALUES (?, ?)",
                    (fund_id, tag_id)
                )

        for fund_slug, entities in SEC_ENTITIES.items():
            fund_id = conn.execute(
                "SELECT id FROM funds WHERE slug = ?", (fund_slug,)
            ).fetchone()[0]
            for entity in entities:
                conn.execute(
                    """
                    INSERT INTO fund_sec_entities (fund_id, cik, legal_name, role)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(fund_id, cik) DO UPDATE SET
                      legal_name=excluded.legal_name, role=excluded.role, active=1
                    """,
                    (fund_id, entity["cik"], entity.get("legal_name"), entity.get("role", "primary")),
                )

if __name__ == "__main__":
    seed()
    print("Database initialized, eight funds seeded, and strategy tags assigned.")
