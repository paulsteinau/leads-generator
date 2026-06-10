# pipeline/scraper/website_content.py
"""
Extracts all meaningful content from an existing website.
Returns a dict usable as context for demo generation.
"""
import asyncio
import base64
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


async def _extract_bg_images(page) -> list[str]:
    """Extract CSS background-image URLs from computed styles."""
    urls = await page.evaluate("""
        () => {
            const seen = new Set();
            for (const el of document.querySelectorAll('*')) {
                const bg = getComputedStyle(el).backgroundImage;
                if (bg && bg !== 'none' && bg.includes('url(')) {
                    const m = bg.match(/url\\(["']?([^"')]+)["']?\\)/);
                    if (m && m[1].startsWith('http')) seen.add(m[1]);
                }
                if (seen.size >= 5) break;
            }
            return [...seen];
        }
    """)
    return urls or []


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
        "bg_images": [],
        "raw_text": "",
        "screenshot_b64": "",
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
                    const skip = new Set(['script','style','noscript','svg','path','header','nav','footer']);
                    function walk(el) {
                        if (skip.has(el.tagName?.toLowerCase())) return '';
                        if (el.nodeType === 3) return el.textContent;
                        return [...el.childNodes].map(walk).join(' ');
                    }
                    return walk(document.body)
                        .replace(/\\s+/g, ' ')
                        .trim()
                        .slice(0, 10000);
                }
            """)
            result["raw_text"] = raw or ""

            # Crawl all internal subpages (skip legal/cookie pages)
            SKIP_KEYWORDS = ["impressum", "datenschutz", "privacy", "cookie", "agb", "widerruf",
                             "nutzungsbedingungen", "sitemap", "login", "cart", "warenkorb", "wp-admin"]
            all_links = await page.evaluate("""
                () => [...document.querySelectorAll('a[href]')]
                    .map(a => a.href)
                    .filter(h => h && !h.includes('#'))
            """)
            from urllib.parse import urlparse, urlunparse
            base = urlparse(url).netloc
            seen_paths = set()
            subpages_to_visit = []
            for link in all_links:
                try:
                    parsed = urlparse(link)
                    if parsed.netloc != base:
                        continue
                    path_lower = parsed.path.lower()
                    if any(kw in path_lower for kw in SKIP_KEYWORDS):
                        continue
                    clean = urlunparse(parsed._replace(query="", fragment=""))
                    if clean == url or parsed.path in seen_paths or parsed.path == "/":
                        continue
                    seen_paths.add(parsed.path)
                    subpages_to_visit.append(clean)
                except Exception:
                    continue

            subpage_texts = []
            for sub_url in subpages_to_visit[:12]:  # max 12 subpages
                try:
                    sub_page = await ctx.new_page()
                    await sub_page.goto(sub_url, timeout=15000, wait_until="domcontentloaded")
                    await asyncio.sleep(1)
                    sub_text = await sub_page.evaluate("""
                        () => {
                            const skip = new Set(['script','style','noscript','svg','path','nav','footer']);
                            function walk(el) {
                                if (skip.has(el.tagName?.toLowerCase())) return '';
                                if (el.nodeType === 3) return el.textContent;
                                return [...el.childNodes].map(walk).join(' ');
                            }
                            return walk(document.body).replace(/\\s+/g, ' ').trim().slice(0, 3000);
                        }
                    """)
                    if sub_text and len(sub_text.strip()) > 100:
                        subpage_texts.append(f"[{sub_url}]:\n{sub_text.strip()}")
                    await sub_page.close()
                except Exception:
                    pass

            if subpage_texts:
                result["subpage_text"] = "\n\n---\n\n".join(subpage_texts)

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

            # Two screenshots: hero (0) + mid section (800px scroll)
            page_height = await page.evaluate("() => document.body.scrollHeight")
            lead_shots = []
            for scroll_y in [0, 800]:
                if scroll_y > 0 and scroll_y >= page_height:
                    break
                await page.evaluate(f"window.scrollTo(0, {scroll_y})")
                await asyncio.sleep(0.2)
                shot = await page.screenshot(type="jpeg", quality=80, full_page=False)
                lead_shots.append(base64.b64encode(shot).decode())
            result["screenshot_b64"] = lead_shots[0] if lead_shots else ""
            result["screenshots"] = lead_shots

            # Colors + images + CSS background images
            result["colors"] = await _extract_colors(page)
            result["images"] = await _extract_images(page)
            result["bg_images"] = await _extract_bg_images(page)

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
