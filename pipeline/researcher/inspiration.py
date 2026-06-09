# pipeline/researcher/inspiration.py
"""
For a given business category, generate design notes for use in demo generation.
Results are cached per category in the industry_patterns DB table (7-day TTL).
"""
from pipeline.utils.claude_p import claude_p

CATEGORY_REFERENCES: dict[str, list[str]] = {
    "Zahnarzt": ["zahnarztpraxis-muehlenbeck.de", "zahnarzt-am-dom.de"],
    "Anwalt": ["kanzlei-woelfel.de", "ra-berlin.de"],
    "Immobilienmakler": ["engel-voelkers.de", "dahler.com"],
    "Physiotherapie": ["physio-berlin.de", "physiozentrum-mitte.de"],
    "Küchenstudio": ["nobilia.de", "bulthaup.com"],
    "Schönheitsklinik": ["aesthetik-berlin.de"],
    "Friseur": ["hairsalon-berlin.de"],
    "Steuerberater": ["stb-berlin.de"],
    "Handwerker": ["handwerker-berlin.de"],
    "Umzugsfirma": ["movinga.de"],
    "Druckerei": ["print24.com", "flyeralarm.de"],
}

DESIGN_ARCHETYPES: dict[str, str] = {
    "Zahnarzt": "Clean medical trust: white backgrounds, calming blues/greens, clear CTAs for appointments, professional photography",
    "Anwalt": "Authoritative and serious: dark navy or charcoal, serif typography, formal layout, trust signals prominent",
    "Immobilienmakler": "Luxury property feel: full-bleed photography, elegant serif/sans mix, property listings grid, premium brand",
    "Physiotherapie": "Wellness and health: soft warm tones, welcoming photography, easy online booking CTA, human-centered",
    "Küchenstudio": "Premium product showcase: lifestyle photography, dark elegant backgrounds, bento grid product cards",
    "Schönheitsklinik": "Luxury beauty: minimalist white, soft rose/gold accents, before/after photos, premium and aspirational",
    "Friseur": "Creative and personal: strong brand color, portfolio gallery, team photos, simple booking flow",
    "Steuerberater": "Trustworthy professional: clean corporate, blue/grey tones, clear service list, credentials prominent",
    "Handwerker": "Reliable and local: strong contrast, before/after work photos, clear phone CTA, trust badges",
    "Umzugsfirma": "Efficient and clear: bold typography, quick quote CTA, process steps, customer reviews",
    "Druckerei": "Products and quality: bright product photos, calculator/configurator CTA, turnaround times prominent",
}


def get_inspiration_notes(category: str, conn=None, lead_id: int = 0) -> str:
    """
    Return design notes for the given category.
    Cached per category in industry_patterns (7-day TTL). Falls back to live Claude call.
    """
    # Check DB cache
    if conn:
        cached = conn.execute(
            "SELECT pattern_data FROM industry_patterns"
            " WHERE industry_tag=? AND (expires_at IS NULL OR expires_at > datetime('now'))",
            (category,),
        ).fetchone()
        if cached:
            return cached[0]

    archetype = DESIGN_ARCHETYPES.get(
        category,
        "Modern professional service: clean layout, clear CTAs, trust signals, mobile-first"
    )
    refs = CATEGORY_REFERENCES.get(category, [])

    prompt = (
        f"You are a senior web designer specializing in German SMB websites.\n"
        f"Business category: {category}\n"
        f"Design archetype: {archetype}\n"
        f"Known design direction for this category: {', '.join(refs) if refs else 'none'}\n\n"
        f"Write 5-8 specific design notes for a premium demo website in this category. "
        f"Cover: color palette (hex values), typography style, hero section, key sections to include, "
        f"CTA placement, and one unique design element that makes it stand out. "
        f"Be concrete and specific. No generic advice. Max 300 words."
    )

    notes = claude_p(
        prompt=prompt,
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        conn=conn,
        lead_id=lead_id,
        stage="inspiration",
    )

    result = f"Category: {category}\nArchetype: {archetype}\n\nDesign Notes:\n{notes}"

    # Store in DB cache
    if conn:
        conn.execute(
            "INSERT OR REPLACE INTO industry_patterns (industry_tag, pattern_data, expires_at)"
            " VALUES (?, ?, datetime('now', '+7 days'))",
            (category, result),
        )
        conn.commit()

    return result
