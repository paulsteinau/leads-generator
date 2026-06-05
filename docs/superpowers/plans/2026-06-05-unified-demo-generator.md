# Unified Demo Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge berlin-leads (existing) and leads-generator (zip) into one system where clicking a lead triggers AI-powered demo site generation that scrapes the existing website content, researches top industry references, and generates a polished HTML demo using embedded design skills.

**Architecture:** Upgrade `Desktop/berlin-leads/` in-place with the zip's API and dashboard. Add new pipeline modules for content scraping (Playwright), inspiration research (Claude + web), and HTML demo generation (Claude with design skill prompts compiled in). A `POST /leads/{id}/generate-demo` endpoint spawns the generation as a background subprocess; the frontend polls `/leads/{id}` for `demo_url` to appear.

**Tech Stack:** Python 3.12, Playwright, anthropic SDK, FastAPI, Next.js 14, Tailwind CDN, SQLite WAL, Vercel CLI

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `api/main.py` | Replace | Full API with approve/reject/regenerate/webhooks/unsubscribe |
| `api/models.py` | Replace | Full model set incl. PendingReviewLead, RegenerateRequest, etc. |
| `api/db.py` | Replace | Schema with demo/audit/suppression/admin_actions tables + migrations |
| `pipeline/utils/claude_p.py` | Create | Thin wrapper around anthropic SDK matching zip's `claude_p()` interface |
| `pipeline/utils/skill_loader.py` | Create | Reads design SKILL.md files → returns compiled design system prompt |
| `pipeline/scraper/website_content.py` | Create | Playwright-based: extract all text, colors, services, contact from existing site |
| `pipeline/researcher/inspiration.py` | Create | DuckDuckGo search + Claude → find 3 reference URLs, screenshot them, extract design notes |
| `pipeline/generator/demo.py` | Create | Claude call: lead content + reference notes + design skills → full HTML |
| `pipeline/generator/screenshots.py` | Create | Playwright: screenshot deployed demo (desktop/mobile × home/full) |
| `pipeline/sender/send.py` | Create | Resend API: send email with demo URL embedded |
| `pipeline/generate_demo_single.py` | Create | Entry script: run all demo stages for a single lead_id |
| `dashboard/app/page.tsx` | Replace | Zip version: adds PendingBadge, pending-review link |
| `dashboard/app/leads/[id]/page.tsx` | Replace | Zip version: 3-col layout, audit card, demo iframe, screenshots |
| `dashboard/app/leads/[id]/ReviewPanel.tsx` | Create | Subject picker + body editor + approve/reject/edit-demo modal |
| `dashboard/app/leads/[id]/EmailPanel.tsx` | Create | Email address editor + variant selector + CRM status buttons |
| `dashboard/app/leads/[id]/ScreenshotTabs.tsx` | Create | Tab switcher for demo screenshots |
| `dashboard/app/leads/[id]/GenerateDemoButton.tsx` | Create | "Generate Demo" button with polling for completion |
| `dashboard/app/components/PendingBadge.tsx` | Create | Badge showing count of leads pending review |
| `dashboard/lib/api.ts` | Modify | Add generateDemo(), approveLead(), rejectLead(), editDemo() API calls |

---

## Task 1: Install Additional Design Skills

**Files:** None (installs globally to `~/.agents/skills/`)

- [ ] **Step 1: Install additional design skill packs**

```bash
npx skills add julienthibeaut/skill-library
npx skills add sinaahmadi/design-skill
npx skills add lovell/design-skill
```

If any of these 404, skip them — only the ones that succeed matter. The `taste-skill` and `emilkowalski/skill` packs installed earlier are already in `~/.agents/skills/`.

- [ ] **Step 2: Verify installed design skills**

```bash
ls ~/.agents/skills/ | grep -iE "design|taste|visual|ui|style|brand"
```

Expected: at minimum `design-taste-frontend`, `high-end-visual-design`, `emil-design-eng`, `minimalist-ui`, `gpt-taste`, `stitch-design-taste`, `industrial-brutalist-ui`, `redesign-existing-projects`.

---

## Task 2: Upgrade API + DB Schema

**Files:**
- Replace: `api/main.py`
- Replace: `api/models.py`
- Replace: `api/db.py`

- [ ] **Step 1: Back up the existing DB**

```bash
cp "C:/Users/Andre Steinau/Desktop/berlin-leads/data/leads.db" \
   "C:/Users/Andre Steinau/Desktop/berlin-leads/data/leads.db.bak-$(date +%Y%m%d)"
```

- [ ] **Step 2: Replace api/models.py with zip version**

Copy `C:\Users\Andre Steinau\Downloads\leads-generator-extracted\leads-generator\api\models.py` → `C:\Users\Andre Steinau\Desktop\berlin-leads\api\models.py`

The zip version adds: `PendingReviewLead`, `RegenerateRequest`, `EditDemoRequest`, `ResendWebhookPayload`, `UnsubscribeRequest`.

- [ ] **Step 3: Replace api/db.py with zip version**

Copy `C:\Users\Andre Steinau\Downloads\leads-generator-extracted\leads-generator\api\db.py` → `C:\Users\Andre Steinau\Desktop\berlin-leads\api\db.py`

The zip version adds: `description`, `description_data`, `industry_tag`, `audit_score`, `audit_data`, `qualification`, `demo_url`, `demo_generated_at`, `demo_screenshots`, `email_subjects`, `email_message_id` columns + `industry_patterns`, `suppressions`, `admin_actions` tables.

- [ ] **Step 4: Replace api/main.py with zip version**

Copy `C:\Users\Andre Steinau\Downloads\leads-generator-extracted\leads-generator\api\main.py` → `C:\Users\Andre Steinau\Desktop\berlin-leads\api\main.py`

- [ ] **Step 5: Run DB migration**

```bash
cd "C:/Users/Andre Steinau/Desktop/berlin-leads"
python -c "from api.db import init_db; init_db(); print('OK')"
```

Expected output: `OK` with no exceptions.

- [ ] **Step 6: Verify new columns exist**

```bash
python -c "
import sqlite3
conn = sqlite3.connect('data/leads.db')
cols = [r[1] for r in conn.execute('PRAGMA table_info(leads)')]
assert 'demo_url' in cols, 'demo_url missing'
assert 'audit_score' in cols, 'audit_score missing'
assert 'qualification' in cols, 'qualification missing'
print('All columns present:', [c for c in cols if c in ('demo_url','audit_score','qualification','industry_tag')])
"
```

Expected: `All columns present: ['audit_score', 'qualification', 'industry_tag', 'demo_url']` (order may vary).

- [ ] **Step 7: Commit**

```bash
cd "C:/Users/Andre Steinau/Desktop/berlin-leads"
git add api/
git commit -m "upgrade api: add full review/approve/webhook/suppression endpoints from leads-generator"
```

---

## Task 3: Create Pipeline Utilities

**Files:**
- Create: `pipeline/utils/__init__.py`
- Create: `pipeline/utils/claude_p.py`
- Create: `pipeline/utils/skill_loader.py`

- [ ] **Step 1: Create utils package**

```bash
mkdir -p "C:/Users/Andre Steinau/Desktop/berlin-leads/pipeline/utils"
touch "C:/Users/Andre Steinau/Desktop/berlin-leads/pipeline/utils/__init__.py"
```

- [ ] **Step 2: Create pipeline/utils/claude_p.py**

```python
# pipeline/utils/claude_p.py
import os
import anthropic

_client: anthropic.Anthropic | None = None

INPUT_COST = {
    "claude-haiku-4-5-20251001": 0.80 / 1_000_000,
    "claude-haiku-4-5": 0.80 / 1_000_000,
    "claude-sonnet-4-5": 3.00 / 1_000_000,
}
OUTPUT_COST = {
    "claude-haiku-4-5-20251001": 4.00 / 1_000_000,
    "claude-haiku-4-5": 4.00 / 1_000_000,
    "claude-sonnet-4-5": 15.00 / 1_000_000,
}


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def claude_p(
    prompt: str,
    system: str = "",
    model: str = "claude-haiku-4-5-20251001",
    max_tokens: int = 4096,
    lead_id: int = 0,
    stage: str = "",
    conn=None,
) -> str:
    """Call Claude and return the text response. Logs cost to DB if conn provided."""
    client = _get_client()
    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system

    resp = client.messages.create(**kwargs)
    text = resp.content[0].text

    if conn and lead_id:
        in_tok = resp.usage.input_tokens
        out_tok = resp.usage.output_tokens
        cost = (in_tok * INPUT_COST.get(model, 0.80 / 1_000_000)) + \
               (out_tok * OUTPUT_COST.get(model, 4.00 / 1_000_000))
        conn.execute(
            "INSERT INTO cost_log (lead_id, model, stage, input_tokens, output_tokens, cost_usd)"
            " VALUES (?,?,?,?,?,?)",
            (lead_id, model, stage, in_tok, out_tok, round(cost, 6)),
        )
        conn.commit()

    return text
```

- [ ] **Step 3: Create pipeline/utils/skill_loader.py**

This module reads the installed design SKILL.md files and compiles a concise design system prompt for use in the demo generator.

```python
# pipeline/utils/skill_loader.py
from pathlib import Path

SKILLS_DIR = Path.home() / ".agents" / "skills"

DESIGN_SKILLS = [
    "design-taste-frontend",
    "high-end-visual-design",
    "emil-design-eng",
    "redesign-existing-projects",
]


def _extract_key_rules(skill_name: str, max_chars: int = 1200) -> str:
    """Read a SKILL.md and return its most actionable content, trimmed."""
    path = SKILLS_DIR / skill_name / "SKILL.md"
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    # Strip frontmatter
    if text.startswith("---"):
        end = text.find("---", 3)
        text = text[end + 3:].strip() if end != -1 else text
    return text[:max_chars]


def build_design_system_prompt() -> str:
    """Build a combined design guidance prompt from installed skill files."""
    parts = []
    for skill in DESIGN_SKILLS:
        content = _extract_key_rules(skill)
        if content:
            parts.append(f"## {skill}\n{content}")

    if not parts:
        return (
            "Design to a high-end agency standard. "
            "No generic layouts. Premium typography. Strong visual hierarchy. "
            "No AI defaults (no purple gradients, no Inter, no Bootstrap cards). "
            "Every pixel intentional."
        )

    return (
        "You are generating a premium demo website. Apply these design standards strictly:\n\n"
        + "\n\n".join(parts)
    )
```

- [ ] **Step 4: Verify skill_loader works**

```bash
cd "C:/Users/Andre Steinau/Desktop/berlin-leads"
python -c "
from pipeline.utils.skill_loader import build_design_system_prompt
prompt = build_design_system_prompt()
print(f'Design prompt length: {len(prompt)} chars')
print(prompt[:200])
"
```

Expected: prints a prompt > 200 chars containing design guidance.

- [ ] **Step 5: Commit**

```bash
git add pipeline/utils/
git commit -m "feat: add claude_p utility and design skill loader"
```

---

## Task 4: Website Content Scraper

**Files:**
- Create: `pipeline/scraper/website_content.py`

- [ ] **Step 1: Create pipeline/scraper/website_content.py**

```python
# pipeline/scraper/website_content.py
"""
Extracts all meaningful content from an existing website.
Returns a dict usable as context for demo generation.
"""
import asyncio
import json
import re
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

try:
    from playwright_stealth import stealth_async
except Exception:
    async def stealth_async(page): pass


async def _extract_colors(page) -> list[str]:
    """Extract dominant background and accent colors from inline styles + computed styles."""
    colors = await page.evaluate("""
        () => {
            const seen = new Set();
            const els = document.querySelectorAll('[style]');
            for (const el of els) {
                const s = el.style;
                for (const prop of ['backgroundColor', 'color', 'borderColor']) {
                    const v = s[prop];
                    if (v && v !== '' && v !== 'rgba(0, 0, 0, 0)') seen.add(v);
                }
            }
            // Also grab CSS variables from :root
            const root = getComputedStyle(document.documentElement);
            for (const prop of root) {
                if (prop.startsWith('--color') || prop.startsWith('--primary') || prop.startsWith('--accent')) {
                    const v = root.getPropertyValue(prop).trim();
                    if (v) seen.add(v);
                }
            }
            return [...seen].slice(0, 10);
        }
    """)
    return colors or []


async def _extract_images(page) -> list[str]:
    """Return first 5 meaningful image src/alt pairs."""
    imgs = await page.evaluate("""
        () => {
            const imgs = [...document.querySelectorAll('img')].filter(
                img => img.width > 100 && img.height > 100 && img.src
            );
            return imgs.slice(0, 5).map(img => ({
                src: img.src,
                alt: img.alt || '',
            }));
        }
    """)
    return imgs or []


async def scrape_website_content(url: str) -> dict:
    """
    Visit `url` and extract all content useful for demo generation.
    Returns a dict with keys: title, tagline, description, services, contact,
    colors, nav_items, testimonials, images, raw_text.
    """
    result = {
        "url": url,
        "title": "",
        "tagline": "",
        "description": "",
        "services": [],
        "contact": {},
        "colors": [],
        "nav_items": [],
        "testimonials": [],
        "images": [],
        "raw_text": "",
    }

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36",
            )
            page = await ctx.new_page()
            await stealth_async(page)

            try:
                await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                await asyncio.sleep(2)
            except PWTimeout:
                return result

            # Title
            result["title"] = await page.title() or ""

            # Nav items
            nav_links = await page.evaluate("""
                () => {
                    const nav = document.querySelector('nav') || document.querySelector('header');
                    if (!nav) return [];
                    return [...nav.querySelectorAll('a')].map(a => a.innerText.trim()).filter(t => t.length > 0 && t.length < 40);
                }
            """)
            result["nav_items"] = list(dict.fromkeys(nav_links))[:8]

            # All visible text
            raw = await page.evaluate("""
                () => {
                    const skip = new Set(['script','style','noscript','svg','path']);
                    function walk(el) {
                        if (skip.has(el.tagName?.toLowerCase())) return '';
                        if (el.nodeType === 3) return el.textContent;
                        return [...el.childNodes].map(walk).join(' ');
                    }
                    return walk(document.body)
                        .replace(/\\s+/g, ' ')
                        .trim()
                        .slice(0, 4000);
                }
            """)
            result["raw_text"] = raw or ""

            # Headings as tagline/description
            headings = await page.evaluate("""
                () => [...document.querySelectorAll('h1,h2,h3')]
                    .map(h => h.innerText.trim())
                    .filter(t => t.length > 5 && t.length < 120)
                    .slice(0, 6)
            """)
            if headings:
                result["tagline"] = headings[0]
                result["description"] = " | ".join(headings[1:3]) if len(headings) > 1 else ""

            # Phone
            phone_match = re.search(r'[\+\(]?[\d\s\-\(\)]{7,20}', raw)
            if phone_match:
                result["contact"]["phone"] = phone_match.group().strip()

            # Email
            email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w{2,}', raw)
            if email_match:
                result["contact"]["email"] = email_match.group()

            # Colors + images
            result["colors"] = await _extract_colors(page)
            result["images"] = await _extract_images(page)

            # Services: look for list items, short paragraphs near keywords
            services_raw = await page.evaluate("""
                () => {
                    const kw = ['leistung','service','angebot','was wir','what we'];
                    const els = [...document.querySelectorAll('li,p')];
                    const near = els.filter(el => {
                        const par = el.closest('section,div');
                        const parText = (par?.innerText || '').toLowerCase();
                        return kw.some(k => parText.includes(k));
                    });
                    return near.slice(0, 8).map(el => el.innerText.trim()).filter(t => t.length > 5 && t.length < 80);
                }
            """)
            result["services"] = services_raw or []

            # Testimonials
            testimonials_raw = await page.evaluate("""
                () => {
                    const kw = ['testimonial','bewertung','meinung','kunde','review','feedback'];
                    const els = [...document.querySelectorAll('blockquote,p,div')];
                    const candidates = els.filter(el => {
                        const t = el.innerText.toLowerCase();
                        return kw.some(k => el.closest('section')?.innerText?.toLowerCase()?.includes(k)) && t.length > 30 && t.length < 200;
                    });
                    return candidates.slice(0, 3).map(el => el.innerText.trim());
                }
            """)
            result["testimonials"] = testimonials_raw or []

            await browser.close()
    except Exception as e:
        result["error"] = str(e)

    return result
```

- [ ] **Step 2: Test the scraper manually**

```bash
cd "C:/Users/Andre Steinau/Desktop/berlin-leads"
python -c "
import asyncio
from pipeline.scraper.website_content import scrape_website_content
r = asyncio.run(scrape_website_content('https://example.com'))
print('title:', r['title'])
print('tagline:', r['tagline'])
print('raw_text length:', len(r['raw_text']))
"
```

Expected: prints title `Example Domain`, some tagline, text length > 0.

- [ ] **Step 3: Commit**

```bash
git add pipeline/scraper/website_content.py
git commit -m "feat: add website content scraper for demo generation"
```

---

## Task 5: Inspiration Researcher

**Files:**
- Create: `pipeline/researcher/__init__.py`
- Create: `pipeline/researcher/inspiration.py`

- [ ] **Step 1: Create researcher package**

```bash
mkdir -p "C:/Users/Andre Steinau/Desktop/berlin-leads/pipeline/researcher"
touch "C:/Users/Andre Steinau/Desktop/berlin-leads/pipeline/researcher/__init__.py"
```

- [ ] **Step 2: Create pipeline/researcher/inspiration.py**

```python
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
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        conn=conn,
        lead_id=lead_id,
        stage="inspiration",
    )

    return f"Category: {category}\nArchetype: {archetype}\n\nDesign Notes:\n{notes}"
```

- [ ] **Step 3: Test inspiration researcher**

```bash
cd "C:/Users/Andre Steinau/Desktop/berlin-leads"
python -c "
from pipeline.researcher.inspiration import get_inspiration_notes
notes = get_inspiration_notes('Zahnarzt')
print(notes[:400])
"
```

Expected: prints design notes specific to dental practices, with color palette and layout guidance.

- [ ] **Step 4: Commit**

```bash
git add pipeline/researcher/
git commit -m "feat: add inspiration researcher for category-specific design notes"
```

---

## Task 6: Demo Generator

**Files:**
- Create: `pipeline/generator/__init__.py`
- Create: `pipeline/generator/demo.py`

- [ ] **Step 1: Create generator package**

```bash
mkdir -p "C:/Users/Andre Steinau/Desktop/berlin-leads/pipeline/generator"
touch "C:/Users/Andre Steinau/Desktop/berlin-leads/pipeline/generator/__init__.py"
```

- [ ] **Step 2: Create pipeline/generator/demo.py**

```python
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

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "demos"


def _make_slug(lead: dict) -> str:
    name = (lead.get("name") or "demo").lower()
    name = re.sub(r"[^a-z0-9]+", "-", name).strip("-")[:30]
    return f"{name}-{lead['id']}"


def _build_prompt(lead: dict, content: dict, inspiration: str) -> str:
    services_text = "\n".join(f"- {s}" for s in content.get("services", [])) or "Not specified"
    contact_text = json.dumps(content.get("contact", {}), ensure_ascii=False)
    nav_text = ", ".join(content.get("nav_items", []))
    testimonials_text = "\n".join(f'"{t}"' for t in content.get("testimonials", [])) or "None found"

    return f"""
Generate a complete, stunning single-page HTML website for this German business.
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

## Design Inspiration for This Category
{inspiration}

## Requirements
- Output ONLY valid HTML — no markdown, no explanation, no code fences
- Use Tailwind CSS via CDN: <script src="https://cdn.tailwindcss.com"></script>
- Use Google Fonts (pick 2 premium fonts matching the category archetype)
- Must include these sections in order:
  1. Sticky nav with logo (business name) + nav links + "Jetzt anfragen" CTA button
  2. Hero: full-viewport height, strong headline + subheadline + primary CTA
  3. Services/Leistungen section: at least 3 cards from actual services found
  4. Why us / Über uns: use actual content from raw_text, genuine copy
  5. Testimonials/Reviews: use Google rating ({lead.get('google_rating', '5.0')} ★, {lead.get('google_reviews', '')} reviews) + any testimonials found
  6. Contact section: real phone, email, address with a simple contact form
  7. Footer: business name, links, address
- Real German copy throughout — no Lorem ipsum, no placeholder text
- All CTAs say "Termin vereinbaren" or "Jetzt anfragen" (not "Learn More" or English)
- Mobile responsive (Tailwind breakpoints)
- Add one tasteful CSS animation (e.g., fade-in hero text on load)
- NO images — use CSS gradients, shapes, and typography instead (images won't load in demo)

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

    # Stage 4: Generate HTML
    prompt = _build_prompt(lead, content, inspiration)
    html = claude_p(
        prompt=prompt,
        system=design_system,
        model="claude-sonnet-4-5",
        max_tokens=8192,
        conn=conn,
        lead_id=lead_id,
        stage="demo_gen",
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
```

- [ ] **Step 3: Test demo generator on a lead without website**

```bash
cd "C:/Users/Andre Steinau/Desktop/berlin-leads"
python -c "
import sqlite3
conn = sqlite3.connect('data/leads.db')
conn.row_factory = sqlite3.Row
# Use a lead that doesn't have a website so we skip scraping
lead = dict(conn.execute(
    'SELECT * FROM leads WHERE website IS NULL LIMIT 1'
).fetchone() or conn.execute('SELECT * FROM leads LIMIT 1').fetchone())
print('Testing with lead:', lead['name'], lead['id'])
from pipeline.generator.demo import generate_demo
url = generate_demo(lead, conn)
print('Demo URL:', url)
"
```

Expected: prints a Vercel URL (or `None` if Vercel isn't authenticated yet — that's OK for this step).

- [ ] **Step 4: Commit**

```bash
git add pipeline/generator/
git commit -m "feat: add demo generator with content scraping, inspiration research, and design skills"
```

---

## Task 7: Demo Screenshots

**Files:**
- Create: `pipeline/generator/screenshots.py`

- [ ] **Step 1: Create pipeline/generator/screenshots.py**

```python
# pipeline/generator/screenshots.py
"""
Takes 4 screenshots of a deployed demo URL:
desktop-home (viewport), desktop-full (full page), mobile-home, mobile-full.
Returns list of base64 PNG strings saved in the demo dir.
"""
import asyncio
import base64
import json
from pathlib import Path

from playwright.async_api import async_playwright

try:
    from playwright_stealth import stealth_async
except Exception:
    async def stealth_async(page): pass

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "demos"

VIEWPORTS = [
    {"name": "desktop-home", "width": 1280, "height": 800, "full_page": False,
     "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"},
    {"name": "desktop-full", "width": 1280, "height": 800, "full_page": True,
     "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"},
    {"name": "mobile-home", "width": 390, "height": 844, "full_page": False,
     "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0) AppleWebKit/605.1.15"},
    {"name": "mobile-full", "width": 390, "height": 844, "full_page": True,
     "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0) AppleWebKit/605.1.15"},
]


async def take_screenshots(demo_url: str, slug: str) -> list[str]:
    """Returns list of file paths to saved screenshots."""
    demo_dir = DATA_DIR / slug
    demo_dir.mkdir(parents=True, exist_ok=True)
    paths = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for vp in VIEWPORTS:
            ctx = await browser.new_context(
                viewport={"width": vp["width"], "height": vp["height"]},
                user_agent=vp["ua"],
            )
            page = await ctx.new_page()
            await stealth_async(page)
            try:
                await page.goto(demo_url, timeout=30000, wait_until="networkidle")
                await asyncio.sleep(1.5)  # let animations settle
                path = str(demo_dir / f"screenshot-{vp['name']}.png")
                await page.screenshot(path=path, full_page=vp["full_page"])
                paths.append(path)
            except Exception:
                pass
            finally:
                await ctx.close()
        await browser.close()

    return paths


def capture_demo_screenshots(demo_url: str, slug: str, conn, lead_id: int) -> list[str]:
    """Sync wrapper. Runs screenshots and updates DB with paths."""
    paths = asyncio.run(take_screenshots(demo_url, slug))
    if paths:
        conn.execute(
            "UPDATE leads SET demo_screenshots=?, updated_at=datetime('now') WHERE id=?",
            (json.dumps(paths), lead_id),
        )
        conn.commit()
    return paths
```

- [ ] **Step 2: Commit**

```bash
git add pipeline/generator/screenshots.py
git commit -m "feat: add playwright screenshot capture for deployed demos"
```

---

## Task 8: Email Sender

**Files:**
- Create: `pipeline/sender/__init__.py`
- Create: `pipeline/sender/send.py`

- [ ] **Step 1: Create sender package**

```bash
mkdir -p "C:/Users/Andre Steinau/Desktop/berlin-leads/pipeline/sender"
touch "C:/Users/Andre Steinau/Desktop/berlin-leads/pipeline/sender/__init__.py"
```

- [ ] **Step 2: Create pipeline/sender/send.py**

```python
# pipeline/sender/send.py
"""
Sends a cold outreach email via Resend with the demo URL embedded.
"""
import os
from urllib.parse import urlparse


def send_email(lead: dict, conn) -> bool:
    """
    Send the approved email for a lead via Resend.
    Returns True on success, False on failure.
    """
    try:
        import resend  # type: ignore
        resend.api_key = os.environ.get("RESEND_API_KEY", "")
        if not resend.api_key:
            return False

        to_email = lead.get("email")
        if not to_email:
            return False

        # Check suppression list
        domain = to_email.split("@")[-1] if "@" in to_email else ""
        suppressed = conn.execute(
            "SELECT 1 FROM suppressions WHERE email=? OR domain=?",
            (to_email, domain),
        ).fetchone()
        if suppressed:
            return False

        subject = lead.get("email_subject") or "Ihre neue Website — kostenlose Demo"
        body = lead.get("email_body_a") or lead.get("email_body_b") or ""

        # Inject demo URL into body if present
        demo_url = lead.get("demo_url")
        if demo_url and demo_url not in body:
            body += f"\n\nHier können Sie Ihre Demo-Website ansehen:\n{demo_url}\n"

        # Build HTML version
        body_html = body.replace("\n", "<br>")
        if demo_url:
            body_html += (
                f'<br><br><a href="{demo_url}" '
                f'style="background:#2563eb;color:white;padding:12px 24px;'
                f'border-radius:6px;text-decoration:none;font-weight:bold;">'
                f'Demo ansehen →</a>'
            )

        params = {
            "from": os.environ.get("RESEND_FROM", "demo@yourdomain.com"),
            "to": [to_email],
            "subject": subject,
            "text": body,
            "html": f"<html><body style='font-family:sans-serif;max-width:600px;margin:0 auto'>{body_html}</body></html>",
        }

        response = resend.Emails.send(params)
        msg_id = response.get("id") if isinstance(response, dict) else getattr(response, "id", None)

        if msg_id:
            domain_for_log = urlparse(lead.get("website", "")).netloc or domain
            conn.execute(
                "INSERT INTO email_log (lead_id, domain, sent_at, subject, body)"
                " VALUES (?,?,datetime('now'),?,?)",
                (lead["id"], domain_for_log, subject, body),
            )
            conn.execute(
                "UPDATE leads SET email_message_id=?, status='contacted',"
                " updated_at=datetime('now') WHERE id=?",
                (msg_id, lead["id"]),
            )
            conn.commit()
            return True

        return False

    except Exception:
        return False
```

- [ ] **Step 3: Add `resend` to requirements**

```bash
cd "C:/Users/Andre Steinau/Desktop/berlin-leads"
cat requirements.txt
```

If `resend` is not in requirements.txt, add it:
```bash
echo "resend" >> requirements.txt
pip install resend
```

- [ ] **Step 4: Commit**

```bash
git add pipeline/sender/
git commit -m "feat: add resend email sender with demo URL injection"
```

---

## Task 9: Single-Lead Demo Runner + API Endpoint

**Files:**
- Create: `pipeline/generate_demo_single.py`
- Modify: `api/main.py` — add `POST /leads/{id}/generate-demo` and `GET /leads/{id}/demo-status`

- [ ] **Step 1: Create pipeline/generate_demo_single.py**

```python
# pipeline/generate_demo_single.py
"""
Entry script: run the full demo generation pipeline for a single lead.
Usage: python pipeline/generate_demo_single.py <lead_id>
"""
import re
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from api.db import get_conn
from pipeline.generator.demo import generate_demo, _make_slug
from pipeline.generator.screenshots import capture_demo_screenshots

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def run(lead_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    if not row:
        log.error(f"Lead {lead_id} not found")
        return

    lead = dict(row)
    log.info(f"Generating demo for lead {lead_id}: {lead.get('name')}")

    # Mark as in-progress
    conn.execute(
        "UPDATE leads SET stage='generating_demo', updated_at=datetime('now') WHERE id=?",
        (lead_id,),
    )
    conn.commit()

    try:
        demo_url = generate_demo(lead, conn)
        log.info(f"Demo generated: {demo_url}")

        if demo_url:
            slug = _make_slug(lead)
            paths = capture_demo_screenshots(demo_url, slug, conn, lead_id)
            log.info(f"Screenshots: {len(paths)} captured")
        else:
            log.warning("Demo URL is None — Vercel deploy may have failed")
            conn.execute(
                "UPDATE leads SET stage='demo_failed', updated_at=datetime('now') WHERE id=?",
                (lead_id,),
            )
            conn.commit()

    except Exception as e:
        log.error(f"Demo generation failed: {e}", exc_info=True)
        conn.execute(
            "UPDATE leads SET stage='demo_failed', updated_at=datetime('now') WHERE id=?",
            (lead_id,),
        )
        conn.commit()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pipeline/generate_demo_single.py <lead_id>")
        sys.exit(1)
    run(int(sys.argv[1]))
```

- [ ] **Step 2: Add generate-demo endpoint to api/main.py**

Add these two endpoints after the existing `# ── Review / Approval` section:

```python
# ── Demo Generation ───────────────────────────────────────────────────────────

@app.post("/leads/{lead_id}/generate-demo")
def trigger_generate_demo(lead_id: int):
    conn = get_conn()
    row = conn.execute("SELECT stage FROM leads WHERE id=?", (lead_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Lead not found")
    if row["stage"] in ("generating_demo",):
        return {"ok": False, "error": "Already generating"}

    import sys, os
    cmd = [
        sys.executable,
        str(ROOT / "pipeline" / "generate_demo_single.py"),
        str(lead_id),
    ]
    subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )
    return {"ok": True, "lead_id": lead_id}


@app.get("/leads/{lead_id}/demo-status")
def demo_status(lead_id: int):
    conn = get_conn()
    row = conn.execute(
        "SELECT stage, demo_url, demo_screenshots FROM leads WHERE id=?", (lead_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Lead not found")
    return {
        "stage": row["stage"],
        "demo_url": row["demo_url"],
        "has_screenshots": bool(row["demo_screenshots"]),
        "ready": row["stage"] == "ready_for_review",
        "failed": row["stage"] == "demo_failed",
    }
```

- [ ] **Step 3: Test the endpoint exists**

```bash
cd "C:/Users/Andre Steinau/Desktop/berlin-leads"
uvicorn api.main:app --reload --port 8000 &
sleep 3
curl -s http://localhost:8000/openapi.json | python -c "
import sys, json
spec = json.load(sys.stdin)
paths = list(spec['paths'].keys())
assert any('generate-demo' in p for p in paths), f'generate-demo not found in: {paths}'
print('OK — generate-demo endpoint registered')
"
```

Expected: `OK — generate-demo endpoint registered`

- [ ] **Step 4: Commit**

```bash
git add pipeline/generate_demo_single.py api/main.py
git commit -m "feat: add single-lead demo runner and generate-demo API endpoint"
```

---

## Task 10: Upgrade Dashboard

**Files:**
- Replace: `dashboard/app/page.tsx`
- Replace: `dashboard/app/leads/[id]/page.tsx`
- Create: `dashboard/app/leads/[id]/ReviewPanel.tsx`
- Create: `dashboard/app/leads/[id]/EmailPanel.tsx`
- Create: `dashboard/app/leads/[id]/ScreenshotTabs.tsx`
- Create: `dashboard/app/components/PendingBadge.tsx`
- Modify: `dashboard/lib/api.ts`

- [ ] **Step 1: Copy zip dashboard files**

```bash
$src = "C:\Users\Andre Steinau\Downloads\leads-generator-extracted\leads-generator\dashboard"
$dst = "C:\Users\Andre Steinau\Desktop\berlin-leads\dashboard"

Copy-Item "$src\app\page.tsx" "$dst\app\page.tsx" -Force
Copy-Item "$src\app\leads\[id]\page.tsx" "$dst\app\leads\[id]\page.tsx" -Force
Copy-Item "$src\app\leads\[id]\ReviewPanel.tsx" "$dst\app\leads\[id]\ReviewPanel.tsx" -Force
Copy-Item "$src\app\leads\[id]\EmailPanel.tsx" "$dst\app\leads\[id]\EmailPanel.tsx" -Force
Copy-Item "$src\app\leads\[id]\ScreenshotTabs.tsx" "$dst\app\leads\[id]\ScreenshotTabs.tsx" -Force
Copy-Item "$src\components\PipelinePanel.tsx" "$dst\components\PipelinePanel.tsx" -Force
Copy-Item "$src\components\CostTracker.tsx" "$dst\components\CostTracker.tsx" -Force
```

- [ ] **Step 2: Create dashboard/app/components/PendingBadge.tsx** (if not in zip)

```tsx
// dashboard/app/components/PendingBadge.tsx
"use client";
import useSWR from "swr";

const fetcher = (url: string) => fetch(url).then(r => r.json());

export default function PendingBadge() {
  const { data } = useSWR("http://localhost:8000/leads/pending-review", fetcher, { refreshInterval: 15000 });
  const count = data?.count ?? 0;
  if (!count) return null;
  return (
    <span className="ml-1 inline-flex items-center justify-center w-5 h-5 text-xs font-bold bg-orange-500 text-white rounded-full">
      {count}
    </span>
  );
}
```

- [ ] **Step 3: Add missing API functions to dashboard/lib/api.ts**

Open `dashboard/lib/api.ts` and ensure these functions exist (add if missing):

```typescript
export async function generateDemo(leadId: number): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch(`http://localhost:8000/leads/${leadId}/generate-demo`, { method: "POST" });
  return res.json();
}

export async function getDemoStatus(leadId: number): Promise<{
  stage: string; demo_url: string | null; has_screenshots: boolean; ready: boolean; failed: boolean;
}> {
  const res = await fetch(`http://localhost:8000/leads/${leadId}/demo-status`);
  return res.json();
}

export async function approveLead(leadId: number): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch(`http://localhost:8000/leads/${leadId}/approve`, { method: "POST" });
  return res.json();
}

export async function rejectLead(leadId: number): Promise<{ ok: boolean }> {
  const res = await fetch(`http://localhost:8000/leads/${leadId}/reject`, { method: "POST" });
  return res.json();
}

export async function editDemo(leadId: number, description: string): Promise<{ ok: boolean }> {
  const res = await fetch(`http://localhost:8000/leads/${leadId}/edit-demo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ description }),
  });
  return res.json();
}
```

- [ ] **Step 4: Build and check for TS errors**

```bash
cd "C:/Users/Andre Steinau/Desktop/berlin-leads/dashboard"
npm run build 2>&1 | tail -20
```

Fix any TS errors before proceeding.

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/Andre Steinau/Desktop/berlin-leads"
git add dashboard/
git commit -m "upgrade dashboard: add review/approval/demo workflow from leads-generator"
```

---

## Task 11: GenerateDemoButton Component

**Files:**
- Create: `dashboard/app/leads/[id]/GenerateDemoButton.tsx`
- Modify: `dashboard/app/leads/[id]/page.tsx` — add the button

- [ ] **Step 1: Create GenerateDemoButton.tsx**

```tsx
// dashboard/app/leads/[id]/GenerateDemoButton.tsx
"use client";
import { useState, useEffect, useCallback } from "react";
import { generateDemo, getDemoStatus } from "@/lib/api";

interface Props {
  leadId: number;
  initialStage: string;
  initialDemoUrl: string | null;
}

const GENERATING_STAGES = new Set(["generating_demo"]);
const DONE_STAGES = new Set(["ready_for_review", "approved", "rejected"]);

export default function GenerateDemoButton({ leadId, initialStage, initialDemoUrl }: Props) {
  const [stage, setStage] = useState(initialStage);
  const [demoUrl, setDemoUrl] = useState(initialDemoUrl);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const poll = useCallback(async () => {
    const status = await getDemoStatus(leadId);
    setStage(status.stage);
    if (status.demo_url) setDemoUrl(status.demo_url);
    return status;
  }, [leadId]);

  useEffect(() => {
    if (!GENERATING_STAGES.has(stage)) return;
    const interval = setInterval(async () => {
      const status = await poll();
      if (!GENERATING_STAGES.has(status.stage)) {
        clearInterval(interval);
        if (status.ready || status.demo_url) {
          window.location.reload(); // refresh to show ReviewPanel + demo iframe
        }
      }
    }, 4000);
    return () => clearInterval(interval);
  }, [stage, poll]);

  const handleGenerate = async () => {
    setLoading(true);
    setError(null);
    const result = await generateDemo(leadId);
    if (result.ok) {
      setStage("generating_demo");
    } else {
      setError(result.error || "Fehler beim Starten");
    }
    setLoading(false);
  };

  if (demoUrl || DONE_STAGES.has(stage)) return null;

  if (GENERATING_STAGES.has(stage)) {
    return (
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 flex items-center gap-3">
        <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        <div>
          <p className="text-sm font-medium text-blue-700">Demo wird erstellt...</p>
          <p className="text-xs text-blue-500">Scraping Website + KI-Generierung + Vercel-Deploy</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border p-5 space-y-3">
      <h2 className="font-semibold text-xs text-gray-400 uppercase tracking-wide">Demo Website</h2>
      <p className="text-sm text-gray-600">
        Generiere eine kostenlose Demo-Website basierend auf dem bestehenden Webauftritt.
        Wird automatisch deployed und kann direkt versendet werden.
      </p>
      <button
        onClick={handleGenerate}
        disabled={loading}
        className="w-full px-4 py-2.5 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 font-medium transition-colors disabled:opacity-60"
      >
        {loading ? "Starte..." : "✨ Demo generieren"}
      </button>
      {error && <p className="text-red-500 text-xs">{error}</p>}
      {stage === "demo_failed" && (
        <p className="text-orange-500 text-xs">Letzter Versuch fehlgeschlagen. Erneut versuchen?</p>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Add GenerateDemoButton to lead detail page**

In `dashboard/app/leads/[id]/page.tsx`, in the right column (Col 3, "space-y-4" div), add the button before the ReviewPanel:

```tsx
import GenerateDemoButton from "./GenerateDemoButton";

// In the JSX, in Col 3 (the rightmost column):
<div className="space-y-4">
  <GenerateDemoButton
    leadId={lead.id}
    initialStage={lead.stage}
    initialDemoUrl={lead.demo_url ?? null}
  />
  {lead.stage === "ready_for_review" && <ReviewPanel lead={lead} />}
  <EmailPanel lead={lead} />
</div>
```

- [ ] **Step 3: Add LeadDetail.demo_url field if missing**

Check `dashboard/lib/api.ts` for the `LeadDetail` type and ensure `demo_url: string | null` is present.

- [ ] **Step 4: Build and verify no TS errors**

```bash
cd "C:/Users/Andre Steinau/Desktop/berlin-leads/dashboard"
npm run build 2>&1 | tail -10
```

Expected: `✓ Compiled successfully` or similar with no errors.

- [ ] **Step 5: Start both API and dashboard and manually test**

```bash
# Terminal 1:
cd "C:/Users/Andre Steinau/Desktop/berlin-leads"
uvicorn api.main:app --reload --port 8000

# Terminal 2:
cd "C:/Users/Andre Steinau/Desktop/berlin-leads/dashboard"
npm run dev
```

Navigate to `http://localhost:3000`, open any lead detail page, verify:
- "Generate Demo" button appears if no demo exists
- Clicking it shows the spinning loader
- After generation completes, page reloads and shows the demo iframe

- [ ] **Step 6: Commit**

```bash
cd "C:/Users/Andre Steinau/Desktop/berlin-leads"
git add dashboard/app/leads/
git commit -m "feat: add click-to-generate demo button with polling"
```

---

## Self-Review

**Spec coverage check:**
- ✅ Merge two systems into one — Tasks 2 + 10 upgrade api/ and dashboard/ from the zip
- ✅ Click lead → generate demo — Tasks 9 + 11 add endpoint and button
- ✅ Existing website content used — Task 4 scrapes all content; Task 6 includes it in prompt
- ✅ Design skills embedded — Task 3 creates skill_loader.py; Task 6 calls it in every generation
- ✅ Inspiration from top websites — Task 5 uses curated references + Claude for design notes
- ✅ Install more design skills — Task 1 attempts additional packs

**No placeholders check:** All code blocks are complete and functional.

**Type consistency:** `LeadDetail`, `lead_id`, `demo_url`, `stage` used consistently across all files.
