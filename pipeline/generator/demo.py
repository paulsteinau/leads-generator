# pipeline/generator/demo.py
"""
Generates a premium React demo website for a lead.
Uses: lead data + scraped content + category inspiration + design skills.
Builds with Vite and deploys to Vercel.
"""
import asyncio
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from pipeline.scraper.website_content import scrape_website_content
from pipeline.researcher.inspiration import get_inspiration_notes
from pipeline.utils.claude_p import claude_p
from pipeline.utils.skill_loader import build_design_system_prompt

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent.parent / "data")) / "demos"
TEMPLATE_DIR = Path(__file__).parent.parent / "react-template"
NPM_CACHE_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent.parent / "data")) / ".npm-cache"


def _make_slug(lead: dict) -> str:
    name = (lead.get("name") or "demo").lower()
    name = re.sub(r"[^a-z0-9]+", "-", name).strip("-")[:30]
    return f"{name}-{lead['id']}"


def _build_prompt(lead: dict, content: dict, inspiration: str, slug: str) -> str:
    services_text = "\n".join(f"- {s}" for s in content.get("services", [])) or "Not specified"
    nav_text = ", ".join(content.get("nav_items", []))
    testimonials_text = "\n".join(f'"{t}"' for t in content.get("testimonials", [])) or "None found"

    scraped_images = content.get("images", [])
    if scraped_images:
        img_lines = "\n".join(
            f'  src="{i.get("src", "")}" alt="{i.get("alt", "")}"'
            for i in scraped_images[:6]
            if i.get("src", "").startswith("http")
        )
        image_section = (
            f"## Real Images from Their Current Website\n"
            f"Use these as <img src={{...}}> props where appropriate:\n{img_lines}"
        )
    else:
        image_section = "## Images\nNo real images — use Picsum placeholders with descriptive seeds."

    screenshot_context = ""
    if content.get("screenshot_b64"):
        screenshot_context = (
            "You are viewing a screenshot of their current website above. "
            "Dramatically improve the design quality while preserving all real content.\n\n"
        )

    return f"""
{screenshot_context}Generate a complete single-file React App.jsx for this German business demo website.

## Business Info
Name: {lead.get('name', '')}
Category: {lead.get('category', '')}
District: {lead.get('district', 'Berlin')}
Address: {lead.get('address', '')}
Phone: {lead.get('phone', '') or content.get('contact', {}).get('phone', '')}
Email: {lead.get('email', '') or content.get('contact', {}).get('email', '')}
Website: {lead.get('website', '')}
Google Rating: {lead.get('google_rating', '')} ({lead.get('google_reviews', '')} Bewertungen)

## Existing Website Content (USE AS SOURCE MATERIAL — do not invent facts)
Current title: {content.get('title', '')}
Current tagline: {content.get('tagline', '')}
Current description: {content.get('description', '')}
Navigation: {nav_text}
Services found:
{services_text}
Testimonials found:
{testimonials_text}
Raw text excerpt: {content.get('raw_text', '')[:1200]}

{image_section}

## Picsum Placeholder Seeds (use these exact seeds for sections without real images)
Hero: https://picsum.photos/seed/{slug}-hero/1600/900
Service 1: https://picsum.photos/seed/{slug}-s1/800/600
Service 2: https://picsum.photos/seed/{slug}-s2/800/600
Service 3: https://picsum.photos/seed/{slug}-s3/800/600
About: https://picsum.photos/seed/{slug}-about/1200/800

## Design Inspiration
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
- Sections in order: Nav, Hero, Leistungen, Über uns, Bewertungen, Kontakt, Footer
""".strip()


def _setup_demo_dir(demo_dir: Path) -> None:
    """Copy React template into demo_dir."""
    if demo_dir.exists():
        shutil.rmtree(demo_dir)
    shutil.copytree(TEMPLATE_DIR, demo_dir)
    (demo_dir / "src").mkdir(exist_ok=True)


def _build_react(demo_dir: Path) -> bool:
    """Run npm install + vite build. Returns True on success."""
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


def _deploy_to_vercel(dist_dir: Path, slug: str) -> str | None:
    """Deploy built dist/ to Vercel and return the live URL."""
    try:
        result = subprocess.run(
            ["vercel", "--yes", "--name", f"lead-{slug}", "--prod"],
            cwd=str(dist_dir),
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
        content = {"raw_text": "", "services": [], "contact": {}, "nav_items": [], "testimonials": [], "images": []}

    # Stage 2: Category design inspiration
    inspiration = get_inspiration_notes(
        category=lead.get("category", ""),
        conn=conn,
        lead_id=lead_id,
    )

    # Stage 3: Design system prompt
    design_system = build_design_system_prompt()

    # Stage 4: Generate App.jsx with Claude
    prompt = _build_prompt(lead, content, inspiration, slug)
    screenshot_b64 = content.get("screenshot_b64") or None

    app_jsx = claude_p(
        prompt=prompt,
        system=design_system,
        model="claude-sonnet-4-6",
        max_tokens=16000,
        conn=conn,
        lead_id=lead_id,
        stage="demo_gen",
        image_b64=screenshot_b64,
        image_media_type="image/jpeg",
    )

    # Strip accidental markdown fences
    app_jsx = app_jsx.strip()
    if app_jsx.startswith("```"):
        app_jsx = re.sub(r'^```[^\n]*\n', '', app_jsx)
        app_jsx = re.sub(r'\n```$', '', app_jsx)

    # Stage 5: Set up React project and write App.jsx
    _setup_demo_dir(demo_dir)
    (demo_dir / "src" / "App.jsx").write_text(app_jsx, encoding="utf-8")

    # Stage 6: Build with Vite
    build_ok = _build_react(demo_dir)
    if not build_ok:
        # Save App.jsx for manual inspection even if build failed
        conn.execute(
            "UPDATE leads SET stage='demo_build_failed', updated_at=datetime('now') WHERE id=?",
            (lead_id,),
        )
        conn.commit()
        return None

    # Stage 7: Deploy dist/ to Vercel
    dist_dir = demo_dir / "dist"
    demo_url = _deploy_to_vercel(dist_dir, slug)

    conn.execute(
        "UPDATE leads SET demo_url=?, demo_generated_at=datetime('now'),"
        " stage='ready_for_review', updated_at=datetime('now') WHERE id=?",
        (demo_url, lead_id),
    )
    conn.commit()

    return demo_url
