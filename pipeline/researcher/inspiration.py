# pipeline/researcher/inspiration.py
"""
For a given business category, find 2-3 reference websites known for good design
and return a design-notes string for use as context in demo generation.
"""
from pipeline.utils.claude_p import claude_p

# Curated high-quality reference sites per category (German market)
CATEGORY_REFERENCES: dict[str, list[str]] = {
    "Zahnarzt": ["zahnarztpraxis-muehlenbeck.de", "zahnarzt-am-dom.de", "zahnarzt-charlottenburg.de"],
    "Anwalt": ["kanzlei-woelfel.de", "ra-berlin.de", "anwaltskanzlei-berlin.de"],
    "Immobilienmakler": ["engel-voelkers.de", "immoscout24.de", "dahler.com"],
    "Physiotherapie": ["physio-berlin.de", "physiozentrum-mitte.de", "physio-praxis.de"],
    "Küchenstudio": ["nobilia.de", "bulthaup.com", "siematic.com"],
    "Schönheitsklinik": ["laserbehandlung-berlin.de", "aesthetik-berlin.de", "hautzentrum-berlin.de"],
    "Friseur": ["hairsalon-berlin.de", "friseur-mitte.de", "hairloft-berlin.de"],
    "Steuerberater": ["stb-berlin.de", "steuerberatung-berlin.de", "taxconsult-berlin.de"],
    "Handwerker": ["handwerker-berlin.de", "elektro-berlin.de", "sanitaer-berlin.de"],
    "Umzugsfirma": ["stadtbekannt.de", "movinga.de", "umzug-berlin.de"],
    "Druckerei": ["print24.com", "flyeralarm.de", "druckerei-berlin.de"],
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
    Return a string of design notes for the given category.
    Uses curated archetypes + Claude to generate specific design guidance.
    """
    archetype = DESIGN_ARCHETYPES.get(
        category,
        "Modern professional service: clean layout, clear CTAs, trust signals, mobile-first"
    )
    refs = CATEGORY_REFERENCES.get(category, [])

    prompt = (
        f"You are a senior web designer specializing in German SMB websites.\n"
        f"Business category: {category}\n"
        f"Design archetype: {archetype}\n"
        f"Reference sites known for quality in this category: {', '.join(refs) if refs else 'none specified'}\n\n"
        f"Write 5-8 specific design notes for a premium demo website in this category. "
        f"Cover: color palette (hex values), typography style, hero section, key sections to include, "
        f"CTA placement, and one unique design element that makes it stand out. "
        f"Be concrete and specific. No generic advice. Max 300 words."
    )

    notes = claude_p(
        prompt=prompt,
        model="claude-sonnet-4-6",
        max_tokens=600,
        conn=conn,
        lead_id=lead_id,
        stage="inspiration",
    )

    return f"Category: {category}\nArchetype: {archetype}\n\nDesign Notes:\n{notes}"
