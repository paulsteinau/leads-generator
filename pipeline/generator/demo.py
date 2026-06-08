# pipeline/generator/demo.py
"""
Generates a full, self-contained HTML demo website for a lead.
Uses: lead data + scraped content + category inspiration + design skills.
Deploys to Vercel and returns the live URL.
"""
import asyncio
import json
import os
import re
import subprocess
import time
from pathlib import Path

from pipeline.scraper.website_content import scrape_website_content
from pipeline.researcher.inspiration import get_inspiration_notes
from pipeline.utils.claude_p import claude_p
from pipeline.utils.skill_loader import build_design_system_prompt

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent.parent / "data")) / "demos"


def _make_slug(lead: dict) -> str:
    name = (lead.get("name") or "demo").lower()
    name = re.sub(r"[^a-z0-9]+", "-", name).strip("-")[:30]
    return f"{name}-{lead['id']}"


def _build_prompt(lead: dict, content: dict, inspiration: str, slug: str) -> str:
    services_text = "\n".join(f"- {s}" for s in content.get("services", [])) or "Not specified"
    nav_text = ", ".join(content.get("nav_items", []))
    testimonials_text = "\n".join(f'"{t}"' for t in content.get("testimonials", [])) or "None found"

    # Real images from their existing site
    scraped_images = content.get("images", [])
    if scraped_images:
        img_lines = "\n".join(
            f"  <img src=\"{i.get('src', '')}\" alt=\"{i.get('alt', '')}\">"
            for i in scraped_images[:6]
            if i.get("src", "").startswith("http")
        )
        image_section = f"## Real Images from Their Current Website\nUse these directly in <img> tags where appropriate:\n{img_lines}"
    else:
        image_section = "## Images\nNo real images scraped — use Picsum placeholders only."

    screenshot_context = ""
    if content.get("screenshot_b64"):
        screenshot_context = (
            "You are viewing a screenshot of their current website above. "
            "Your job is to dramatically improve the design quality while preserving every piece of real content.\n\n"
        )

    return f"""
{screenshot_context}Generate a complete, stunning single-page HTML website for this German business.
This is a DEMO to show the business owner what their website COULD look like.
Use ALL the business content provided — don't invent facts. Redesign the presentation.

## Business Info
Name: {lead.get('name', '')}
Category: {lead.get('category', '')}
District: {lead.get('district', 'Berlin')}
Address: {lead.get('address', '')}
Phone: {lead.get('phone', '') or content.get('contact', {}).get('phone', '')}
Email: {lead.get('email', '') or content.get('contact', {}).get('email', '')}
Website: {lead.get('website', '')}
Google Rating: {lead.get('google_rating', '')} ({lead.get('google_reviews', '')} reviews)

## Existing Website Content (USE AS SOURCE MATERIAL)
Current title: {content.get('title', '')}
Current tagline: {content.get('tagline', '')}
Current description: {content.get('description', '')}
Navigation: {nav_text}
Services found:
{services_text}
Testimonials found:
{testimonials_text}
Raw text excerpt: {content.get('raw_text', '')[:800]}

{image_section}

## Design Inspiration for This Category
{inspiration}

## Requirements
- Output ONLY valid HTML — no markdown, no explanation, no code fences
- Use Tailwind CSS via CDN: <script src="https://cdn.tailwindcss.com"></script>
- Use Google Fonts (pick 2 premium fonts matching the category archetype)
- Must include these sections in order:
  1. Sticky nav with logo (business name) + nav links + "Jetzt anfragen" CTA button
  2. Hero: full-viewport height, strong headline + subheadline + primary CTA button
  3. Services/Leistungen: at least 3 cards from actual services found
  4. Why us / Über uns: genuine copy from raw_text
  5. Testimonials/Reviews: Google rating ({lead.get('google_rating', '5.0')} ★, {lead.get('google_reviews', '')} reviews) + any testimonials found
  6. Contact: real phone, email, address + simple contact form
  7. Footer: business name, links, address
- Images: use the real scraped images above where they fit. For any section needing an image without a real one, use Picsum placeholders:
  Hero background: https://picsum.photos/seed/{slug}-hero/1600/900
  Service cards: https://picsum.photos/seed/{slug}-s1/800/500, {slug}-s2, {slug}-s3
  About section: https://picsum.photos/seed/{slug}-about/1200/700
  Always set object-fit: cover and appropriate dimensions.
- Real German copy throughout — no Lorem ipsum, no placeholder text
- All CTAs say "Termin vereinbaren" or "Jetzt anfragen"
- Mobile responsive (Tailwind breakpoints)
- Scroll reveal animations: add this JS block before </body>:
  <script>
  const observer = new IntersectionObserver((entries) => {{
    entries.forEach(e => {{ if (e.isIntersecting) {{ e.target.classList.add('revealed'); observer.unobserve(e.target); }} }});
  }}, {{ threshold: 0.15 }});
  document.querySelectorAll('.reveal').forEach(el => observer.observe(el));
  </script>
  Add CSS: .reveal {{ opacity: 0; transform: translateY(28px); transition: opacity 0.65s ease, transform 0.65s ease; }}
  .revealed {{ opacity: 1; transform: translateY(0); }}
  Apply class "reveal" to: every section heading, service cards, testimonial cards, contact form

Output only the complete HTML file starting with <!DOCTYPE html>.
""".strip()


def _deploy_to_vercel(demo_dir: Path, slug: str) -> str | None:
    """Deploy demo dir to Vercel and return the URL."""
    try:
        result = subprocess.run(
            ["vercel", "--yes", "--name", f"lead-{slug}", "--prod"],
            cwd=str(demo_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
        # Extract URL from output
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("https://"):
                return line
        # Try stderr too
        for line in result.stderr.splitlines():
            line = line.strip()
            if "https://" in line:
                m = re.search(r'https://[^\s]+', line)
                if m:
                    return m.group()
    except Exception:
        pass
    return None


def generate_demo(lead: dict, conn) -> str | None:
    """
    Full demo generation pipeline for a single lead.
    Returns the deployed demo URL, or None on failure.
    Updates the lead record in DB throughout.
    """
    lead_id = lead["id"]
    slug = _make_slug(lead)
    demo_dir = DATA_DIR / slug
    demo_dir.mkdir(parents=True, exist_ok=True)

    # Stage 1: Scrape existing website content
    content: dict = {}
    if lead.get("website"):
        content = asyncio.run(scrape_website_content(lead["website"]))
        (demo_dir / "content.json").write_text(
            json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    else:
        content = {"raw_text": "", "services": [], "contact": {}, "nav_items": [], "testimonials": []}

    # Stage 2: Get category-specific design inspiration
    inspiration = get_inspiration_notes(
        category=lead.get("category", ""),
        conn=conn,
        lead_id=lead_id,
    )

    # Stage 3: Build design system prompt from installed skill files
    design_system = build_design_system_prompt()

    # Stage 4: Generate HTML (with screenshot vision input if available)
    prompt = _build_prompt(lead, content, inspiration, slug)
    screenshot_b64 = content.get("screenshot_b64") or None
    html = claude_p(
        prompt=prompt,
        system=design_system,
        model="claude-sonnet-4-6",
        max_tokens=8192,
        conn=conn,
        lead_id=lead_id,
        stage="demo_gen",
        image_b64=screenshot_b64,
        image_media_type="image/jpeg",
    )

    # Strip any accidental markdown fences
    html = html.strip()
    if html.startswith("```"):
        html = re.sub(r'^```[^\n]*\n', '', html)
        html = re.sub(r'\n```$', '', html)

    (demo_dir / "index.html").write_text(html, encoding="utf-8")

    # Vercel needs a minimal config to serve index.html
    vercel_json = json.dumps({"rewrites": [{"source": "/(.*)", "destination": "/index.html"}]})
    (demo_dir / "vercel.json").write_text(vercel_json, encoding="utf-8")

    # Stage 5: Deploy to Vercel
    demo_url = _deploy_to_vercel(demo_dir, slug)

    # Update DB
    conn.execute(
        "UPDATE leads SET demo_url=?, demo_generated_at=datetime('now'),"
        " stage='ready_for_review', updated_at=datetime('now') WHERE id=?",
        (demo_url, lead_id),
    )
    conn.commit()

    return demo_url
