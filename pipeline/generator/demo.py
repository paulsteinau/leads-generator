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

from pipeline.scraper.website_content import scrape_website_content
from pipeline.researcher.inspiration import get_inspiration_notes
from pipeline.researcher.reference_screenshots import get_all_reference_data
from pipeline.utils.claude_p import claude_p
from pipeline.utils.skill_loader import build_design_system_prompt

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent.parent / "data")) / "demos"
TEMPLATE_DIR = Path(__file__).parent.parent / "react-template"
NPM_CACHE_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent.parent / "data")) / ".npm-cache"


def _make_slug(lead: dict) -> str:
    name = (lead.get("name") or "demo").lower()
    name = re.sub(r"[^a-z0-9]+", "-", name).strip("-")[:30]
    return f"{name}-{lead['id']}"


def _extract_structured_content(raw_text: str, subpage_text: str, category: str, conn, lead_id: int) -> dict:
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


def _build_design_brief_prompt(lead: dict, inspiration: str, ref_css: dict) -> str:
    css_summary = ""
    if ref_css.get("computed"):
        parts = []
        for sel, vals in ref_css["computed"].items():
            if vals.get("font") and vals["font"] not in ("", "inherit"):
                parts.append(f"{sel}: font={vals['font']}, color={vals['color']}, bg={vals['bg']}")
        if parts:
            css_summary = "Extracted from reference site:\n" + "\n".join(parts[:5])

    return (
        f"You are a senior UI/UX designer. Create a concise design brief for a premium German "
        f"{lead.get('category', '')} website.\n\n"
        f"Category archetype:\n{inspiration}\n\n"
        f"{css_summary}\n\n"
        f"Write a design brief with EXACTLY these fields (be concrete, no vague words):\n"
        f"- Color palette: primary hex, secondary hex, accent hex, background hex, text hex\n"
        f"- Font pairing: heading font name (Google Fonts), body font name (Google Fonts)\n"
        f"- Hero layout: one of [full-bleed-photo, split-asymmetric, centered-minimal, editorial-grid]\n"
        f"- Visual mood: exactly 3 adjectives\n"
        f"- Standout element: one specific CSS/animation detail that elevates the design\n\n"
        f"Max 120 words. These values go directly into React/CSS code."
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

    return f"""
{screenshot_context}Generate a complete single-file React App.jsx for this German business demo website.

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

## Existing Website Content (USE AS SOURCE MATERIAL — do not invent facts)
Current title: {content.get('title', '')}
Current tagline: {content.get('tagline', '')}
Navigation: {nav_text}
Services:
{services_text}
Testimonials:
{testimonials_text}
Main page text:
{content.get('raw_text', '')[:10000]}

{f"Additional pages:{chr(10)}{content.get('subpage_text', '')[:8000]}" if content.get('subpage_text') else ""}

{image_section}

## Picsum Placeholder Seeds (use for sections without real images)
Hero: https://picsum.photos/seed/{slug}-hero/1600/900
Service 1: https://picsum.photos/seed/{slug}-s1/800/600
Service 2: https://picsum.photos/seed/{slug}-s2/800/600
Service 3: https://picsum.photos/seed/{slug}-s3/800/600
About: https://picsum.photos/seed/{slug}-about/1200/800

## Design Brief (implement exactly)
{design_brief}

## Category Design Inspiration
{inspiration}

## Output Rules
- Output ONLY valid JSX starting with import statements
- No markdown fences, no explanation text
- File must start with: import React from 'react'
- All components defined in one file, exported as: export default function App()
- Google Fonts: import via a <style> tag rendered in the component, e.g.:
  const FontImport = () => (
    <style>{{`@import url('https://fonts.googleapis.com/css2?family=...');`}}</style>
  )
- Tailwind v4: use utility classes directly, no config needed
- motion/react: import {{ motion, useScroll, useTransform, useInView, useReducedMotion }} from 'motion/react'
- gsap: import {{ gsap }} from 'gsap'; import {{ ScrollTrigger }} from 'gsap/ScrollTrigger'
- Icons: import {{ Phone, MapPin, Star, ArrowRight, CheckCircle, Clock }} from '@phosphor-icons/react'
- All copy in German
- Sections in order: Nav, Hero, Leistungen, Über uns, Prozess (3–4 Schritte), Bewertungen, FAQ (3 Fragen), Kontakt, Footer
- Each section must be fully implemented — no placeholders, no TODOs, no "// add more here" comments
- Add subtle scroll animations (motion/react useInView) on at least 3 sections
- Nav must have a working mobile hamburger menu with animated open/close
- Hero must have a clear primary CTA button
- Kontakt section must show phone, email, address, and a styled contact form
- COMPLETENESS IS MANDATORY: generate the full implementation, minimum 900 lines of JSX
- Do NOT truncate, abbreviate, or simplify any section to save tokens — a complete site is required
""".strip()


def _validate_and_fix_jsx(app_jsx: str, conn=None, lead_id: int = 0) -> str:
    """
    Quick pre-flight: Python checks first, Haiku only if issues found.
    Fixes the most common Vite build failure causes.
    """
    issues = []
    if not app_jsx.strip().startswith("import"):
        issues.append("File does not start with import statements")
    if "export default function App" not in app_jsx:
        issues.append("Missing: export default function App()")
    if app_jsx.count(' class="') > 0:
        issues.append(f"Found {app_jsx.count(' class=\"')} instances of class= (must be className=)")
    if "import React from 'react'" not in app_jsx and 'import React from "react"' not in app_jsx:
        issues.append("Missing: import React from 'react'")

    if not issues:
        return app_jsx

    print(f"[demo] JSX validation found issues: {issues} — calling Haiku to fix...")
    prompt = (
        f"Fix the following issues in this React App.jsx file and return the complete corrected file.\n"
        f"Issues found:\n" + "\n".join(f"- {i}" for i in issues) + "\n\n"
        f"Rules:\n"
        f"- Return ONLY valid JSX, no markdown fences, no explanation\n"
        f"- Fix class= → className=\n"
        f"- Ensure import React from 'react' is first line\n"
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


def _build_react(demo_dir: Path) -> bool:
    NPM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            ["npm", "install", "--cache", str(NPM_CACHE_DIR), "--prefer-offline"],
            cwd=str(demo_dir),
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode != 0:
            print(f"[demo] npm install failed:\n{result.stderr[-2000:]}")
            return False

        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(demo_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            print(f"[demo] vite build failed:\n{result.stderr[-2000:]}")
            return False

        return True
    except Exception as e:
        print(f"[demo] build error: {e}")
        return False


def _deploy_to_vercel(demo_dir: Path, slug: str) -> str | None:
    try:
        result = subprocess.run(
            ["vercel", "deploy", "dist", "--yes", "--name", f"lead-{slug}", "--prod"],
            cwd=str(demo_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("https://"):
                return line
        for line in result.stderr.splitlines():
            if "https://" in line:
                m = re.search(r'https://[^\s]+', line)
                if m:
                    return m.group()
    except Exception as e:
        print(f"[demo] vercel deploy error: {e}")
    return None


def generate_demo(lead: dict, conn) -> str | None:
    """
    Full demo generation pipeline for a single lead.
    Returns the deployed demo URL, or None on failure.
    """
    lead_id = lead["id"]
    slug = _make_slug(lead)
    demo_dir = DATA_DIR / slug

    # Stage 1: Scrape existing website
    content: dict = {}
    if lead.get("website"):
        content = asyncio.run(scrape_website_content(lead["website"]))
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
    inspiration = get_inspiration_notes(category=category, conn=conn, lead_id=lead_id)

    # Stage 4: Haiku — structured content extraction
    print(f"[demo] Extracting structured content for lead {lead_id}...")
    structured = _extract_structured_content(
        raw_text=content.get("raw_text", ""),
        subpage_text=content.get("subpage_text", ""),
        category=category,
        conn=conn,
        lead_id=lead_id,
    )

    # Stage 5: Sonnet — design brief (Sonnet understands design intent better than Haiku)
    print(f"[demo] Generating design brief for lead {lead_id}...")
    design_brief = claude_p(
        prompt=_build_design_brief_prompt(lead, inspiration, ref_css),
        model="claude-sonnet-4-6",
        max_tokens=600,
        conn=conn,
        lead_id=lead_id,
        stage="design_brief",
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
        model="claude-opus-4-8",
        max_tokens=20000,
        conn=conn,
        lead_id=lead_id,
        stage="demo_gen",
        images=images if images else None,
    )

    # Strip accidental markdown fences
    app_jsx = app_jsx.strip()
    if app_jsx.startswith("```"):
        app_jsx = re.sub(r'^```[^\n]*\n', '', app_jsx)
        app_jsx = re.sub(r'\n```$', '', app_jsx)

    # Stage 8.5: Haiku — JSX pre-flight validation
    app_jsx = _validate_and_fix_jsx(app_jsx, conn=conn, lead_id=lead_id)

    # Stage 9: Set up React project and write App.jsx
    _setup_demo_dir(demo_dir)
    (demo_dir / "src" / "App.jsx").write_text(app_jsx, encoding="utf-8")

    # Stage 10: Build with Vite
    build_ok = _build_react(demo_dir)
    if not build_ok:
        conn.execute(
            "UPDATE leads SET stage='demo_build_failed', updated_at=datetime('now') WHERE id=?",
            (lead_id,),
        )
        conn.commit()
        return None

    # Stage 11: Deploy to Vercel
    demo_url = _deploy_to_vercel(demo_dir, slug)

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
