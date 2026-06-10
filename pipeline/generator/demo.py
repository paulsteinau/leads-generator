# pipeline/generator/demo.py
"""
Generates a premium React demo website for a lead.
Flow:
  1. Scrape lead's existing website (content + screenshot)
  2. Load category reference data (cached screenshot + CSS palette)
  3. Haiku: structured content extraction (services, about, key facts)
  4. Haiku: design brief (concrete colors, fonts, layout decisions)
  5. Opus: generate App.jsx with all context + both screenshots
  6. Vite build → Vercel deploy
"""
import asyncio
import json
import os
import random
import re
import shutil
import subprocess
from pathlib import Path

import httpx

from pipeline.scraper.website_content import scrape_website_content
from pipeline.researcher.inspiration import get_inspiration_notes, SCHEMA_TYPES
from pipeline.researcher.reference_screenshots import get_all_reference_data
from pipeline.utils.claude_p import claude_p
from pipeline.utils.skill_loader import build_design_system_prompt

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent.parent / "data")) / "demos"
TEMPLATE_DIR = Path(__file__).parent.parent / "react-template"
NPM_CACHE_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent.parent / "data")) / ".npm-cache"



def _set_sub_stage(conn, lead_id: int, sub_stage: str) -> None:
    conn.execute(
        "UPDATE leads SET demo_sub_stage=?, updated_at=datetime('now') WHERE id=?",
        (sub_stage, lead_id),
    )
    conn.commit()


def _make_slug(lead: dict) -> str:
    name = (lead.get("name") or "demo").lower()
    name = re.sub(r"[^a-z0-9]+", "-", name).strip("-")[:30]
    return f"{name}-{lead['id']}"


def _extract_structured_content(raw_text: str, subpage_text: str, category: str, conn, lead_id: int, generation_num: int = 1) -> dict:
    """Use Haiku to reliably extract services, about text, and key facts from scraped text."""
    combined = raw_text[:8000]
    if subpage_text:
        combined += f"\n\n---SUBPAGES---\n{subpage_text[:4000]}"

    prompt = (
        f"Extract structured information from this German {category} business website text.\n\n"
        f"Return ONLY valid JSON with these fields:\n"
        f"- services: list of strings, each a service or offering (max 10, keep original German wording)\n"
        f"- about: 2-3 sentence summary of who this business is, their story, USPs (in German)\n"
        f"- testimonials: list of customer quote strings found verbatim (max 5)\n"
        f"- phone: phone number string or null\n"
        f"- email: email address string or null\n"
        f"- opening_hours: string description if found, else null\n\n"
        f"Website text:\n{combined}"
    )

    raw = claude_p(
        prompt=prompt,
        model="claude-sonnet-4-6",
        max_tokens=1200,
        conn=conn,
        lead_id=lead_id,
        stage="content_extraction",
        generation_num=generation_num,
    )

    # Strip markdown fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r'^```[^\n]*\n', '', raw)
        raw = re.sub(r'\n```$', '', raw)

    try:
        return json.loads(raw)
    except Exception:
        return {}


# Archetype pools for forced per-generation variance
_VIBE_ARCHETYPES = [
    "Ethereal Glass: deep OLED near-black (#050505), radial mesh gradients with subtle glowing accent orbs, heavy backdrop-blur cards with white/10 hairlines, wide geometric Grotesk typography",
    "Editorial Luxury: warm off-white (#FDFBF7) or deep espresso background, high-contrast display typography, subtle CSS noise/film-grain overlay (opacity 0.03), physical paper feel, editorial spacing",
    "Soft Structuralism: silver-grey or pure white background, massive bold Grotesk headlines, airy floating components with highly diffused ambient shadows, minimalist precision",
    "Dark Industrial: zinc-950 or slate-900 base, single saturated accent (electric blue OR emerald OR hot orange), mono typeface accents, sharp-edged precision, data-forward density",
    "Forest Premium: deep green + bone + amber accent, natural textures, generous whitespace, trustworthy warmth without the cliché beige-brass palette",
]
_LAYOUT_ARCHETYPES = [
    "Asymmetrical Bento: masonry-like CSS Grid of varying card sizes (col-span-8 next to stacked col-span-4), bento cells with real visual variation (images, gradients, not white-on-white)",
    "Z-Axis Cascade: elements stacked like physical cards, slightly overlapping with -2deg/3deg rotation, depth-of-field layers, scroll reveals that unfurl the stack",
    "Editorial Split: massive typography on the left half, interactive image pills or staggered cards on the right, generous negative space, editorial rhythm",
    "Sticky-Stack Scroll: hero pinned, sections stack and replace each other on scroll via GSAP ScrollTrigger, cinematic vertical storytelling",
    "Horizontal Magazine: full-width alternating sections that each use a completely different layout family (no zigzag repetition), section-by-section compositional variety",
]
_HERO_PARADIGMS = [
    "Asymmetric Split Hero — text on one side, hero image on the other, bold headline left-aligned",
    "Scroll-Pinned Hero — hero stays pinned while content slides up behind it (GSAP pin)",
    "Editorial Manifesto Hero — large kinetic type, no asset, almost-poster feel",
    "Full-Bleed Photo Hero — edge-to-edge image, text overlay with scrim, bold single headline",
    "Curtain-Reveal Hero — parts animate in on load like a curtain parting",
]
_MOTION_LEVELS = [6, 7, 7, 8]  # weighted toward higher motion


def _build_design_brief_prompt(lead: dict, inspiration: str, ref_css: dict, structured: dict | None = None) -> str:
    css_summary = ""
    if ref_css.get("computed"):
        parts = []
        for sel, vals in ref_css["computed"].items():
            if vals.get("font") and vals["font"] not in ("", "inherit"):
                parts.append(f"{sel}: font={vals['font']}, color={vals['color']}, bg={vals['bg']}")
        if parts:
            css_summary = "Extracted from reference site:\n" + "\n".join(parts[:5])

    # Business-specific context for a unique brief per lead
    services_preview = ""
    if structured:
        svcs = structured.get("services") or []
        if svcs:
            services_preview = "Key services: " + ", ".join(svcs[:4])

    about_preview = ""
    if structured:
        about = (structured.get("about") or "").strip()
        if about:
            about_preview = f"About: {about[:200]}"

    rating_info = ""
    if lead.get("google_rating"):
        rating_info = f"Google rating: {lead['google_rating']} ({lead.get('google_reviews', '')} reviews)"

    # Randomly select archetypes to force visual variance between generations
    vibe = random.choice(_VIBE_ARCHETYPES)
    layout = random.choice(_LAYOUT_ARCHETYPES)
    hero = random.choice(_HERO_PARADIGMS)
    motion = random.choice(_MOTION_LEVELS)

    return (
        f"You are a senior UI/UX designer. Create a concise, BUSINESS-SPECIFIC design brief for:\n\n"
        f"Business: {lead.get('name', '')} ({lead.get('category', '')}) in {lead.get('district', 'Berlin')}\n"
        f"{services_preview}\n{about_preview}\n{rating_info}\n\n"
        f"Category archetype (inspiration only, do NOT copy directly):\n{inspiration}\n\n"
        f"{css_summary}\n\n"
        f"FORCED DESIGN DIRECTION for this generation (implement exactly):\n"
        f"- Vibe archetype: {vibe}\n"
        f"- Layout archetype: {layout}\n"
        f"- Hero paradigm: {hero}\n"
        f"- Motion intensity: {motion}/10 (implement scroll reveals + hover physics accordingly)\n\n"
        f"Write a design brief with EXACTLY these fields (concrete values, no vague words):\n"
        f"- Color palette: primary hex, secondary hex, accent hex, background hex, text hex\n"
        f"  (Choose colors that fit THIS specific business's personality, NOT the generic {lead.get('category','')} cliché)\n"
        f"- Font pairing: heading font name (Google Fonts), body font name (Google Fonts)\n"
        f"  (Banned as defaults: Inter, Roboto, Arial. Use Geist, Outfit, Cabinet Grotesk, Satoshi, Plus Jakarta Sans, etc.)\n"
        f"- Hero layout: implement the hero paradigm above\n"
        f"- Visual mood: exactly 3 adjectives specific to this business\n"
        f"- Standout element: one specific scroll animation or micro-interaction detail that makes this site memorable\n\n"
        f"Max 150 words. These values go directly into React/CSS code."
    )


def _build_codegen_prompt(
    lead: dict,
    content: dict,
    structured: dict,
    inspiration: str,
    design_brief: str,
    slug: str,
    n_ref_screenshots: int = 0,
    n_lead_screenshots: int = 0,
) -> str:
    # Services: prefer Haiku-extracted, fall back to heuristic
    services_list = structured.get("services") or content.get("services", [])
    services_text = "\n".join(f"- {s}" for s in services_list) or "Not specified"

    # Testimonials: prefer Haiku-extracted
    testimonials_list = structured.get("testimonials") or content.get("testimonials", [])
    testimonials_text = "\n".join(f'"{t}"' for t in testimonials_list) or "None found"

    # About text from Haiku extraction
    about_text = structured.get("about", "")

    # Contact: merge scraped regex + Haiku extraction
    phone = (structured.get("phone") or lead.get("phone") or content.get("contact", {}).get("phone", ""))
    email = (structured.get("email") or lead.get("email") or content.get("contact", {}).get("email", ""))
    opening_hours = structured.get("opening_hours", "")

    nav_text = ", ".join(content.get("nav_items", []))

    # Extract subpage URLs from subpage_text (format: "[url]:\ncontent")
    subpage_urls: list[str] = []
    for line in (content.get("subpage_text") or "").split("\n"):
        line = line.strip()
        if line.startswith("[http") and line.endswith("]:"):
            url = line[1:-2]
            subpage_urls.append(url)

    # Build route map: derive clean slug + label from URL path
    from urllib.parse import urlparse as _urlparse
    routes: list[dict] = []
    seen_slugs: set = set()
    for url in subpage_urls[:8]:
        path = _urlparse(url).path.rstrip("/")
        if not path or path == "/":
            continue
        parts = [p for p in path.split("/") if p]
        route_slug = parts[-1].lower().replace("-", "-").replace("_", "-")[:30]
        if route_slug in seen_slugs:
            continue
        seen_slugs.add(route_slug)
        label = parts[-1].replace("-", " ").replace("_", " ").title()
        routes.append({"url": url, "path": f"/{route_slug}", "label": label})

    routes_section = ""
    if routes:
        route_lines = "\n".join(
            f'  - path="{r["path"]}" label="{r["label"]}" (content from: {r["url"]})'
            for r in routes
        )
        routes_section = f"""
## Subpages to Implement as React Router Routes
The existing website has these subpages — each must become a real route:
{route_lines}

Route "/" is the home/landing page (full marketing page with hero, key sections, CTA).
Each subpage route renders its own dedicated page component with full content from the scraped data.
The Nav must link to all routes and show the active route visually.
"""

    # Parse red flags
    raw_flags = lead.get("red_flags", "[]")
    try:
        flags = json.loads(raw_flags) if isinstance(raw_flags, str) else (raw_flags or [])
    except Exception:
        flags = []

    # Build weakness section
    weakness_lines = []
    ps_mobile = lead.get("pagespeed_mobile")
    ps_desktop = lead.get("pagespeed_desktop")
    seo_score = lead.get("seo_score")
    if ps_mobile is not None:
        weakness_lines.append(f"- Mobile PageSpeed: {ps_mobile}/100{' — critically slow, optimize heavily' if ps_mobile < 50 else ''}")
    if ps_desktop is not None:
        weakness_lines.append(f"- Desktop PageSpeed: {ps_desktop}/100")
    if seo_score is not None:
        weakness_lines.append(f"- SEO Score: {seo_score}/100 — fix with proper structure, headings, meta tags")
    if not lead.get("has_cta"):
        weakness_lines.append("- No CTA found — add prominent booking/contact button above the fold")
    if not lead.get("has_booking"):
        weakness_lines.append("- No booking system — add a clear appointment/contact CTA")
    if not lead.get("is_mobile_ready"):
        weakness_lines.append("- Not mobile-optimized — demo must be fully responsive")
    for flag in flags:
        weakness_lines.append(f"- {flag}")
    weakness_section = (
        "## Known Issues — Fix ALL of These in the Demo\n" + "\n".join(weakness_lines)
        if weakness_lines else ""
    )

    # Images: real <img> tags + CSS background images
    scraped_images = content.get("images", [])
    bg_images = content.get("bg_images", [])
    if scraped_images or bg_images:
        img_lines = "\n".join(
            f'  src="{i.get("src", "")}" alt="{i.get("alt", "")}"'
            for i in scraped_images[:6]
            if i.get("src", "").startswith("http")
        )
        bg_lines = "\n".join(f'  background-image: url("{u}")' for u in bg_images[:3])
        image_section = (
            "## Real Images from Their Current Website\n"
            "Use these as <img src={...}> props where appropriate:\n"
            f"{img_lines}\n"
            + (f"\nCSS background images (use as hero/section backgrounds):\n{bg_lines}" if bg_lines else "")
        )
    else:
        image_section = "## Images\nNo real images found — use Picsum placeholders with descriptive seeds."

    # Screenshot context block — label each image by its index
    screenshot_lines = []
    idx = 1
    if n_ref_screenshots > 0:
        labels = ["hero/nav area", "services/features section", "lower section/footer"]
        for i in range(n_ref_screenshots):
            label = labels[i] if i < len(labels) else f"section {i+1}"
            screenshot_lines.append(f"Image {idx}: Reference site — {label}. Study the design quality, typography, spacing, and color use.")
            idx += 1
    if n_lead_screenshots > 0:
        lead_labels = ["hero/nav area", "mid section"]
        for i in range(n_lead_screenshots):
            label = lead_labels[i] if i < len(lead_labels) else f"section {i+1}"
            screenshot_lines.append(f"Image {idx}: Current lead website — {label}. Dramatically improve this while keeping all real content.")
            idx += 1
    screenshot_context = "\n".join(screenshot_lines) + "\n\n" if screenshot_lines else ""

    schema_type = SCHEMA_TYPES.get(lead.get("category", ""), "LocalBusiness")

    return f"""
{screenshot_context}Generate a complete single-file React App.jsx for this German business demo website.
{routes_section}

## Business Info
Name: {lead.get('name', '')}
Category: {lead.get('category', '')}
District: {lead.get('district', 'Berlin')}
Address: {lead.get('address', '')}
Phone: {phone}
Email: {email}
{f"Opening hours: {opening_hours}" if opening_hours else ""}
Website: {lead.get('website', '')}
Google Rating: {lead.get('google_rating', '')} ({lead.get('google_reviews', '')} Bewertungen)

## About This Business
{about_text or content.get('description', '') or 'No about text found.'}

## Existing Website Content — COPY THIS TEXT VERBATIM
CRITICAL RULE: Every heading, service name, team member, location, testimonial, and body text must come DIRECTLY from the source below. Do NOT invent, paraphrase, or swap in generic text. If a name, city, or service appears in the source — use it exactly. Only invent content where the source has absolutely no equivalent.

Current title: {content.get('title', '')}
Current tagline: {content.get('tagline', '')}
Navigation: {nav_text}
Services:
{services_text}
Testimonials:
{testimonials_text}
Main page text:
{content.get('raw_text', '')[:12000]}

{f"Subpages (USE ALL NAMES, LOCATIONS, SERVICES MENTIONED):{chr(10)}{content.get('subpage_text', '')[:12000]}" if content.get('subpage_text') else ""}

{image_section}

## Picsum Placeholder Seeds (use for sections without real images)
Hero: https://picsum.photos/seed/{slug}-hero/1600/900
Service 1: https://picsum.photos/seed/{slug}-s1/800/600
Service 2: https://picsum.photos/seed/{slug}-s2/800/600
Service 3: https://picsum.photos/seed/{slug}-s3/800/600
About: https://picsum.photos/seed/{slug}-about/1200/800

{weakness_section}

## Design Brief (implement exactly)
{design_brief}

## Category Design Inspiration
{inspiration}

## SEO & AEO Requirements (implement ALL — non-negotiable)

### Meta Tags (set via useEffect on mount)
- document.title: "{lead.get('name', '')} — {lead.get('category', '')} in {lead.get('district', 'Berlin')}"
- meta[name="description"]: 150-160 Zeichen, enthält Hauptleistung + Standort + USP
- meta[property="og:title"], meta[property="og:description"], meta[property="og:locale"] content="de_DE"
- meta[name="robots"] content="index, follow"

### Schema.org JSON-LD (render as <script type="application/ld+json"> in JSX via dangerouslySetInnerHTML)
Primary type: {schema_type}
Required fields: name, address (streetAddress, addressLocality, addressCountry="DE"), telephone, url
If google_rating exists: include aggregateRating (ratingValue + reviewCount)
FAQPage schema: wrap all FAQ question/answer pairs as Question + Answer entities

### Semantic HTML Structure
- Exactly ONE <h1>: business name or primary tagline
- Section titles as <h2>: Leistungen, Über uns, Prozess, Bewertungen, FAQ, Kontakt
- Individual service/feature names as <h3>
- Body text in <p>, lists in <ul>/<li>
- Use semantic elements: <header>, <main>, <section>, <footer>, <nav>, <address>

### AEO Content Structure (for AI search engines)
- FAQ: each question as clear <h3>, answer as 2-3 sentence <p> — direct and factual
- "Über uns": structured paragraph covering who / what / where / since when
- Contact section: NAP (Name, Adresse, Telefon) consistent with business info
- No filler text — every sentence must be scannable and informative

## Output Rules
- Output ONLY valid JSX starting with import statements
- No markdown fences, no explanation text
- React is auto-imported by Vite — do NOT write a bare `import React from 'react'`
  If you need hooks, use ONLY: import {{ useState, useEffect, useRef, useCallback }} from 'react' (once, combined)
  Never write both `import React from 'react'` AND `import {{ useState }} from 'react'` — that causes a build error
- All components defined in one file, exported as: export default function App()
- Google Fonts: import via a <style> tag rendered in the component, e.g.:
  const FontImport = () => (
    <style>{{`@import url('https://fonts.googleapis.com/css2?family=...');`}}</style>
  )
- Tailwind v4: use utility classes directly, no config needed
- motion/react: import {{ motion, useScroll, useTransform, useInView, useReducedMotion }} from 'motion/react'
- gsap: import {{ gsap }} from 'gsap'; import {{ ScrollTrigger }} from 'gsap/ScrollTrigger'
- Icons: ONLY use icons from this verified list — others DO NOT EXIST in the installed package and will break the build:
  Phone, PhoneCall, MapPin, NavigationArrow, Star, StarHalf, StarFour,
  ArrowRight, ArrowLeft, ArrowUp, ArrowDown, ArrowCircleRight,
  CheckCircle, Check, CheckSquare, Clock, Timer, HourglassMedium,
  Heart, HeartStraight, House, HouseLine, User, Users, UserCircle, UserPlus,
  Camera, Image, Images, Calendar, CalendarBlank, CalendarCheck,
  Envelope, EnvelopeSimple, Globe, GlobeSimple, GlobeHemisphereWest,
  MagnifyingGlass, Warning, WarningCircle, Info, Question,
  ShieldCheck, ShieldStar, Trophy, Medal, Leaf, Plant,
  Tag, Tags, Pencil, PencilSimple, Trash, TrashSimple,
  Link, LinkSimple, Share, ShareNetwork, BookOpen, Book, Article,
  ChartBar, ChartLine, ChartPie, TrendUp, TrendDown,
  CreditCard, Wallet, Money, ShoppingCart, ShoppingBag, Storefront, Receipt,
  Stethoscope, FirstAid, Bandaids, Pill, Heartbeat, Activity,
  Wrench, Hammer, Scissors, Ruler, Toolbox, Package,
  Coffee, ForkKnife, Fork, Pizza, Wine, Cake,
  GraduationCap, Student, Barbell, MusicNote, MusicNotes,
  Car, Bicycle, Truck, Airplane,
  CaretDown, CaretUp, CaretRight, CaretLeft, CaretDoubleRight,
  ChevronDown, ChevronUp, ChevronRight, ChevronLeft,
  X, XCircle, Plus, PlusCircle, Minus, DotsThree, DotsThreeVertical,
  List, ListBullets, Eye, EyeSlash, Lock, LockOpen, Key,
  Bell, BellSimple, Chat, ChatCircle, Megaphone, Broadcast,
  SpinnerGap, CircleNotch, Sun, Moon, Cloud, Wind, Thermometer,
  Lightning, Sparkle, Fire, Drop, Snowflake,
  InstagramLogo, FacebookLogo, TwitterLogo, LinkedinLogo, YoutubeLogo, WhatsappLogo
  Example: import {{ Phone, MapPin, Star, CheckCircle, ArrowRight }} from '@phosphor-icons/react'
- React Router: import {{ BrowserRouter, Routes, Route, Link, NavLink, useLocation }} from 'react-router-dom'
- All copy in German

## Routing Architecture
- App() renders: <BrowserRouter><Layout /></BrowserRouter>
- Layout component: sticky Nav + <Outlet /> + Footer (uses useOutlet or nested Routes)
- Route "/" = HomePage: full marketing landing page (hero, key sections, CTAs)
- Additional routes for each subpage listed above — each is its own page component
- Nav uses <NavLink> with active styling (e.g. className={{{{ isActive }}}} => isActive ? 'underline' : '')
- useLocation() for scroll-to-top on route change (useEffect on location.pathname)
- If no subpages found: build a single-page app without router, just scroll sections

## Home Page Structure
- Required: sticky Nav (always first) + Hero + Footer (always last)
- Everything between Hero and Footer: YOU decide what sections fit this specific business
  A law firm: Rechtsgebiete, Team/Anwälte, Referenzen, Kontakt
  A restaurant: Speisekarte highlights, Atmosphäre, Reservierung, Kontakt
  Adapt to the actual business — do NOT default to the same generic order every time

- Each section must be fully implemented — no placeholders, no TODOs, no "// add more here" comments
## ANIMATION PHILOSOPHY
Use motion/react and GSAP where it serves the design — not everywhere by default.
Before adding any animation, ask: what does this communicate? (hierarchy, storytelling, feedback, state change)
Minimum: at least 4 meaningful animations chosen based on what fits THIS specific design.
Available tools: motion/react whileInView stagger, GSAP ScrollTrigger (sticky stack, parallax, horizontal pan), spring physics on interactive elements, clip-path reveals, blur-fade transitions.
Every CTA button must have whileTap={{ scale: 0.97 }}. Beyond that: your judgment.

## DESIGN UNIQUENESS RULE
This website must look VISUALLY DISTINCT from any other website in the same category.
- Do NOT use the generic 3-column equal feature cards layout
- Do NOT use the AI-purple gradient default
- Implement the specific vibe and layout archetype from the Design Brief above
- Every section must use a different layout family (no same layout repeated)

- Nav must have a working mobile hamburger menu with animated open/close (lines morph to X)
- Hero must have a clear primary CTA button
- Kontakt section must show phone, email, address, and a styled contact form
- COMPLETENESS IS MANDATORY: generate the full implementation, minimum 900 lines of JSX
- Do NOT truncate, abbreviate, or simplify any section to save tokens — a complete site is required
""".strip()


def _dedup_react_imports(app_jsx: str) -> str:
    """Merge duplicate React imports — prevents 'React already declared' build error."""
    lines = app_jsx.split("\n")
    react_imports: list[str] = []
    other_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if re.match(r"^import\s+React", stripped) or re.match(r'^import\s*\{[^}]*\}\s*from\s*["\']react["\']', stripped):
            react_imports.append(stripped)
        else:
            other_lines.append(line)
    if len(react_imports) <= 1:
        return app_jsx

    # Merge: collect all named imports + decide if default React is needed
    named: set[str] = set()
    needs_default = False
    for imp in react_imports:
        # `import React from 'react'`
        if re.match(r"^import React from", imp):
            needs_default = True
        # `import React, { useState } from 'react'`
        m = re.match(r"^import React,\s*\{([^}]+)\}", imp)
        if m:
            needs_default = True
            for n in m.group(1).split(","):
                named.add(n.strip())
        # `import { useState, useEffect } from 'react'`
        m = re.match(r"^import\s*\{([^}]+)\}\s*from\s*['\"]react['\"]", imp)
        if m:
            for n in m.group(1).split(","):
                named.add(n.strip())

    if needs_default and named:
        merged = f"import React, {{ {', '.join(sorted(named))} }} from 'react'"
    elif needs_default:
        merged = "import React from 'react'"
    elif named:
        merged = f"import {{ {', '.join(sorted(named))} }} from 'react'"
    else:
        merged = "import React from 'react'"

    print(f"[demo] Merged {len(react_imports)} React imports → {merged}")
    return "\n".join([merged] + other_lines)


_VALID_PHOSPHOR_ICONS: frozenset[str] = frozenset({
    "Phone", "PhoneCall", "MapPin", "NavigationArrow", "Star", "StarHalf", "StarFour",
    "ArrowRight", "ArrowLeft", "ArrowUp", "ArrowDown", "ArrowCircleRight",
    "CheckCircle", "Check", "CheckSquare", "Clock", "Timer", "HourglassMedium",
    "Heart", "HeartStraight", "House", "HouseLine", "User", "Users", "UserCircle", "UserPlus",
    "Camera", "Image", "Images", "Calendar", "CalendarBlank", "CalendarCheck",
    "Envelope", "EnvelopeSimple", "Globe", "GlobeSimple", "GlobeHemisphereWest",
    "MagnifyingGlass", "Warning", "WarningCircle", "Info", "Question",
    "ShieldCheck", "ShieldStar", "Trophy", "Medal", "Leaf", "Plant",
    "Tag", "Tags", "Pencil", "PencilSimple", "Trash", "TrashSimple",
    "Link", "LinkSimple", "Share", "ShareNetwork", "BookOpen", "Book", "Article",
    "ChartBar", "ChartLine", "ChartPie", "TrendUp", "TrendDown",
    "CreditCard", "Wallet", "Money", "ShoppingCart", "ShoppingBag", "Storefront", "Receipt",
    "Stethoscope", "FirstAid", "Bandaids", "Pill", "Heartbeat", "Activity",
    "Wrench", "Hammer", "Scissors", "Ruler", "Toolbox", "Package",
    "Coffee", "ForkKnife", "Fork", "Pizza", "Wine", "Cake",
    "GraduationCap", "Student", "Barbell", "MusicNote", "MusicNotes",
    "Car", "Bicycle", "Truck", "Airplane",
    "CaretDown", "CaretUp", "CaretRight", "CaretLeft", "CaretDoubleRight",
    "ChevronDown", "ChevronUp", "ChevronRight", "ChevronLeft",
    "X", "XCircle", "Plus", "PlusCircle", "Minus", "DotsThree", "DotsThreeVertical",
    "List", "ListBullets", "Eye", "EyeSlash", "Lock", "LockOpen", "Key",
    "Bell", "BellSimple", "Chat", "ChatCircle", "Megaphone", "Broadcast",
    "SpinnerGap", "CircleNotch", "Sun", "Moon", "Cloud", "Wind", "Thermometer",
    "Lightning", "Sparkle", "Fire", "Drop", "Snowflake",
    "InstagramLogo", "FacebookLogo", "TwitterLogo", "LinkedinLogo", "YoutubeLogo", "WhatsappLogo",
})


def _fix_phosphor_imports(app_jsx: str) -> str:
    """Strip any phosphor icon names not in the verified whitelist — prevents 'X is not exported' build errors."""
    phosphor_pattern = re.compile(
        r"^(import\s*\{)([^}]+)(\}\s*from\s*['\"]@phosphor-icons/react['\"];?)",
        re.MULTILINE,
    )
    def _filter_icons(m: re.Match) -> str:
        raw_names = [n.strip() for n in m.group(2).split(",") if n.strip()]
        valid = [n for n in raw_names if n in _VALID_PHOSPHOR_ICONS]
        invalid = [n for n in raw_names if n not in _VALID_PHOSPHOR_ICONS]
        if invalid:
            print(f"[demo] Removed invalid phosphor icons: {invalid}")
        if not valid:
            return ""  # remove the entire import line
        return f"{m.group(1)} {', '.join(valid)} {m.group(3)}"
    result = phosphor_pattern.sub(_filter_icons, app_jsx)
    # Remove any usage of removed icons in JSX (replace <BadIcon with <Star)
    return result


def _validate_and_fix_jsx(app_jsx: str, conn=None, lead_id: int = 0) -> str:
    """
    Quick pre-flight: Python checks first, Haiku only if issues found.
    Fixes the most common Vite build failure causes.
    """
    # Always deduplicate React imports first (no LLM call needed)
    app_jsx = _dedup_react_imports(app_jsx)
    # Strip hallucinated phosphor icon names
    app_jsx = _fix_phosphor_imports(app_jsx)

    issues = []
    if not app_jsx.strip().startswith("import"):
        issues.append("File does not start with import statements")
    if "export default function App" not in app_jsx:
        issues.append("Missing: export default function App()")
    if app_jsx.count(' class="') > 0:
        issues.append(f"Found {app_jsx.count(' class=\"')} instances of class= (must be className=)")

    if not issues:
        return app_jsx

    print(f"[demo] JSX validation found issues: {issues} — calling Haiku to fix...")
    prompt = (
        f"Fix the following issues in this React App.jsx file and return the complete corrected file.\n"
        f"Issues found:\n" + "\n".join(f"- {i}" for i in issues) + "\n\n"
        f"Rules:\n"
        f"- Return ONLY valid JSX, no markdown fences, no explanation\n"
        f"- Fix class= → className=\n"
        f"- React hooks: use `import {{ useState, useEffect }} from 'react'` (no duplicate React imports)\n"
        f"- Ensure export default function App() is present\n\n"
        f"File:\n{app_jsx}"
    )
    fixed = claude_p(
        prompt=prompt,
        model="claude-haiku-4-5",
        max_tokens=20000,
        conn=conn,
        lead_id=lead_id,
        stage="jsx_validation",
    )
    fixed = fixed.strip()
    if fixed.startswith("```"):
        fixed = re.sub(r'^```[^\n]*\n', '', fixed)
        fixed = re.sub(r'\n```$', '', fixed)
    return fixed


def _setup_demo_dir(demo_dir: Path) -> None:
    if demo_dir.exists():
        shutil.rmtree(demo_dir)
    shutil.copytree(TEMPLATE_DIR, demo_dir)
    (demo_dir / "src").mkdir(exist_ok=True)


def _deploy_via_vercel_api(demo_dir: Path, slug: str, conn, lead_id: int) -> str | None:
    """Upload React source to Vercel API — Vercel builds in their cloud, no local npm needed."""
    token = os.environ.get("VERCEL_TOKEN", "")
    if not token:
        print("[demo] VERCEL_TOKEN not set")
        return None

    _set_sub_stage(conn, lead_id, "vercel_deploy")

    # Collect all source files (skip node_modules / dist if they exist)
    files = []
    skip = {"node_modules", "dist", ".git"}
    for path in demo_dir.rglob("*"):
        if path.is_file() and not any(p in skip for p in path.parts):
            rel = path.relative_to(demo_dir).as_posix()
            try:
                files.append({"file": rel, "data": path.read_text(encoding="utf-8")})
            except UnicodeDecodeError:
                import base64
                files.append({"file": rel, "data": base64.b64encode(path.read_bytes()).decode(), "encoding": "base64"})

    payload = {
        "name": f"lead-{slug}",
        "files": files,
        "projectSettings": {
            "buildCommand": "npm run build",
            "outputDirectory": "dist",
            "installCommand": "npm install",
            "framework": None,
        },
        "target": "production",
    }

    try:
        resp = httpx.post(
            "https://api.vercel.com/v13/deployments",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=180,
        )
        data = resp.json()
        if resp.status_code in (200, 201):
            url = data.get("url") or ""
            if url and not url.startswith("https://"):
                url = f"https://{url}"
            print(f"[demo] vercel deploy ok: {url}")
            return url or None
        print(f"[demo] vercel API error {resp.status_code}: {json.dumps(data)[:500]}")
    except Exception as e:
        print(f"[demo] vercel API exception: {e}")
    return None


def generate_demo(lead: dict, conn) -> str | None:
    """
    Full demo generation pipeline for a single lead.
    Returns the deployed demo URL, or None on failure.
    """
    lead_id = lead["id"]
    slug = _make_slug(lead)
    demo_dir = DATA_DIR / slug

    # Compute generation number (how many times has this lead been generated before)
    gen_row = conn.execute(
        "SELECT COUNT(DISTINCT generation_num) FROM cost_log WHERE lead_id=? AND stage='demo_gen'",
        (lead_id,),
    ).fetchone()
    generation_num = (gen_row[0] or 0) + 1

    # Stage 1: Scrape existing website
    _set_sub_stage(conn, lead_id, "scraping")
    content: dict = {}
    if lead.get("website"):
        content = asyncio.run(scrape_website_content(lead["website"]))
        if content.get("error"):
            print(f"[demo] scraping error for lead {lead_id}: {content['error']}")
        else:
            print(f"[demo] scraped lead {lead_id}: {len(content.get('raw_text',''))} chars, {len(content.get('subpage_text',''))} subpage chars, {len(content.get('images',[]))} images")
        (DATA_DIR / slug).mkdir(parents=True, exist_ok=True)
        (DATA_DIR / slug / "content.json").write_text(
            json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    else:
        content = {
            "raw_text": "", "services": [], "contact": {}, "nav_items": [],
            "testimonials": [], "images": [], "bg_images": [],
        }

    # Stage 2: Reference site data — all 3 sites cached, 2 randomly selected per demo
    category = lead.get("category", "")
    all_ref_sites = get_all_reference_data(category)
    selected_sites = random.sample(all_ref_sites, min(2, len(all_ref_sites))) if all_ref_sites else []
    ref_css = selected_sites[0].get("css", {}) if selected_sites else {}

    # Stage 3: Category design inspiration (cached 7 days)
    _set_sub_stage(conn, lead_id, "inspiration")
    inspiration = get_inspiration_notes(category=category, conn=conn, lead_id=lead_id)

    # Stage 4: Haiku — structured content extraction
    _set_sub_stage(conn, lead_id, "content_extraction")
    print(f"[demo] Extracting structured content for lead {lead_id}...")
    structured = _extract_structured_content(
        raw_text=content.get("raw_text", ""),
        subpage_text=content.get("subpage_text", ""),
        category=category,
        conn=conn,
        lead_id=lead_id,
        generation_num=generation_num,
    )

    # Stage 5: Sonnet — design brief (Sonnet understands design intent better than Haiku)
    _set_sub_stage(conn, lead_id, "design_brief")
    print(f"[demo] Generating design brief for lead {lead_id}...")
    design_brief = claude_p(
        prompt=_build_design_brief_prompt(lead, inspiration, ref_css, structured),
        model="claude-sonnet-4-6",
        max_tokens=600,
        conn=conn,
        lead_id=lead_id,
        stage="design_brief",
        generation_num=generation_num,
    )

    # Stage 6: Design system prompt (skills)
    design_system = build_design_system_prompt()

    # Stage 7: Build images list — 2 randomly selected ref sites × 3 shots + 2 lead shots
    ref_screenshots: list[str] = []
    for site_data in selected_sites:
        ref_screenshots.extend(site_data.get("screenshots", [])[:3])

    lead_screenshots = content.get("screenshots") or (
        [content["screenshot_b64"]] if content.get("screenshot_b64") else []
    )
    images: list[tuple[str, str]] = [
        (b64, "image/jpeg") for b64 in ref_screenshots + lead_screenshots if b64
    ]

    # Stage 8: Opus — generate App.jsx
    _set_sub_stage(conn, lead_id, "generating_jsx")
    print(f"[demo] Generating App.jsx with Opus for lead {lead_id} ({len(images)} images)...")
    prompt = _build_codegen_prompt(
        lead=lead,
        content=content,
        structured=structured,
        inspiration=inspiration,
        design_brief=design_brief,
        slug=slug,
        n_ref_screenshots=len(ref_screenshots),
        n_lead_screenshots=len(lead_screenshots),
    )

    app_jsx = claude_p(
        prompt=prompt,
        system=design_system,
        model="claude-fable-5",
        max_tokens=20000,
        conn=conn,
        lead_id=lead_id,
        stage="demo_gen",
        images=images if images else None,
        generation_num=generation_num,
    )

    # Strip accidental markdown fences
    app_jsx = app_jsx.strip()
    if app_jsx.startswith("```"):
        app_jsx = re.sub(r'^```[^\n]*\n', '', app_jsx)
        app_jsx = re.sub(r'\n```$', '', app_jsx)

    # Stage 8.5: Haiku — JSX pre-flight validation
    _set_sub_stage(conn, lead_id, "jsx_validation")
    app_jsx = _validate_and_fix_jsx(app_jsx, conn=conn, lead_id=lead_id)

    # Stage 9: Set up React project and write App.jsx
    _setup_demo_dir(demo_dir)
    (demo_dir / "src" / "App.jsx").write_text(app_jsx, encoding="utf-8")

    # Stage 10+11: Deploy source to Vercel (Vercel builds in their cloud)
    demo_url = _deploy_via_vercel_api(demo_dir, slug, conn, lead_id)

    if demo_url:
        conn.execute(
            "UPDATE leads SET demo_url=?, demo_generated_at=datetime('now'),"
            " stage='ready_for_review', updated_at=datetime('now') WHERE id=?",
            (demo_url, lead_id),
        )
    else:
        conn.execute(
            "UPDATE leads SET stage='demo_deploy_failed', updated_at=datetime('now') WHERE id=?",
            (lead_id,),
        )
    conn.commit()

    return demo_url
