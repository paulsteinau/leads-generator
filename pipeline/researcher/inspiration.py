# pipeline/researcher/inspiration.py
"""
For a given business category, generate design notes for use in demo generation.
Results are cached per category in the industry_patterns DB table (7-day TTL).
"""
from pipeline.utils.claude_p import claude_p

CATEGORY_REFERENCES: dict[str, list[str]] = {
    "Zahnarzt": ["dr-shafe.de", "zahnarzt-hanau.net", "32reasons.de"],
    "Anwalt": ["sk-strafrecht.de", "hp-w.de", "albus.legal"],
    "Immobilienmakler": ["engelvoelkers.com", "von-poll.com", "dahler.com"],
    "Physiotherapie": ["noirboutiquegym.de", "koerperwerk.com", "physioloungefrankfurt.de"],
    "Küchenstudio": ["siematic.com", "next125.com", "leicht.com"],
    "Architekt": ["aff-architekten.com", "sauerbruchhutton.de", "baumschlager-eberle.com"],
    "Handwerker": ["holzmanufaktur.com", "baumeisterwerk.de", "hecbau.de", "lbm-energiewerke.de"],
    "Steuerberater": ["warringsholz.de", "taxboutique-steuerberatung.de", "roedl.com"],
    "Schönheitsklinik": ["aesthetify.de", "aiva-institut.de", "drmertz.de"],
    "Umzugsfirma": ["movinga.com", "getbellhops.com", "puremovers.com"],
    "Friseur": ["blackexcellence.berlin", "gentlemen-barberclubs.de", "steventabach.com"],
}

DESIGN_ARCHETYPES: dict[str, str] = {
    "Zahnarzt": "Clean medical trust: white backgrounds, calming blues/greens, clear CTAs for appointments, professional photography. Reference: 32reasons.de (award-winning 2025), dr-shafe.de",
    "Anwalt": "Authoritative and serious: dark navy or charcoal, clean sans-serif, minimal layout, trust signals prominent. Not too playful. Reference: sk-strafrecht.de, hp-w.de, albus.legal",
    "Immobilienmakler": "Luxury property feel: full-bleed photography, elegant serif/sans mix, premium brand positioning. Reference: engelvoelkers.com, von-poll.com, dahler.com",
    "Physiotherapie": "Premium boutique wellness: dark or neutral tones, editorial photography, high-end studio feel. Reference: noirboutiquegym.de, koerperwerk.com, physioloungefrankfurt.de",
    "Küchenstudio": "Premium product showcase: full-screen lifestyle photography, minimal navigation, lots of whitespace, brand-forward. Reference: siematic.com, next125.com, leicht.com",
    "Architekt": "Portfolio-driven minimalism: generous whitespace, project photography, refined typography, no clutter. Reference: aff-architekten.com, sauerbruchhutton.de, baumschlager-eberle.com",
    "Handwerker": "Premium craft positioning: warm materials photography, clean layout, quality signals, before/after work. Reference: holzmanufaktur.com, baumeisterwerk.de",
    "Steuerberater": "Modern professional: clean and approachable, boutique feel, credentials prominent, not stiff. Reference: warringsholz.de, taxboutique-steuerberatung.de, roedl.com",
    "Schönheitsklinik": "Light luxury aesthetics: white/light backgrounds, minimal, premium medical beauty brand. Reference: aesthetify.de, aiva-institut.de, drmertz.de",
    "Umzugsfirma": "Tech-forward and efficient: bold typography, quick quote CTA, process steps, customer reviews. Reference: movinga.com, getbellhops.com",
    "Friseur": "Premium urban barbershop: dark editorial aesthetic, strong photography, confident brand identity. Reference: blackexcellence.berlin, gentlemen-barberclubs.de",
}


SCHEMA_TYPES: dict[str, str] = {
    "Zahnarzt": "Dentist",
    "Anwalt": "LegalService",
    "Immobilienmakler": "RealEstateAgent",
    "Physiotherapie": "PhysicalTherapy",
    "Küchenstudio": "HomeAndConstructionBusiness",
    "Architekt": "Architect",
    "Handwerker": "HomeAndConstructionBusiness",
    "Steuerberater": "AccountingService",
    "Schönheitsklinik": "BeautySalon",
    "Umzugsfirma": "MovingCompany",
    "Friseur": "HairSalon",
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
