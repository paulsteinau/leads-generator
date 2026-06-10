CATEGORIES = [
    "Zahnarzt", "Anwalt", "Immobilienmakler",  # High-ROI first
    "Physiotherapie", "Küchenstudio", "Architekt",
    "Handwerker", "Steuerberater", "Schönheitsklinik",
    "Umzugsfirma", "Friseur",
]

DISTRICTS = [
    "Mitte", "Prenzlauer Berg", "Kreuzberg", "Charlottenburg",
    "Friedrichshain", "Neukölln", "Steglitz", "Tempelhof",
    "Pankow", "Lichtenberg",
]


def all_queries() -> list[dict]:
    return [
        {"query": f"{cat} Berlin {dist}", "category": cat, "district": dist}
        for cat in CATEGORIES
        for dist in DISTRICTS
    ]


def get_daily_queries(conn, n: int = 22) -> list[dict]:
    recent = {r["query"] for r in conn.execute(
        "SELECT query FROM search_runs WHERE ran_at > datetime('now', '-3 days')"
    ).fetchall()}
    candidates = [q for q in all_queries() if q["query"] not in recent]
    if not candidates:
        candidates = all_queries()
    return candidates[:n]
