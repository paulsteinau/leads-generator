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


async def _dismiss_cookie_banners(page) -> None:
    """Attempt to dismiss common German/EU cookie consent banners."""
    # Known vendor-specific selectors — most reliable, try first
    vendor_selectors = [
        "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",  # Cookiebot
        "#onetrust-accept-btn-handler",                             # OneTrust
        ".klaro .cm button.btn-success",                            # Klaro
        "#BorlabsCookieBtn",                                        # Borlabs
        "button#accept-all-cookies",
        "button[data-consent-action='acceptAll']",
        "button[data-cookiebanner='accept_button']",
        "button[class*='accept-all']",
        "button[id*='accept-all']",
        "button[id*='acceptAll']",
        "button[class*='acceptAll']",
        "button[data-action='accept']",
        ".cc-btn.cc-allow",                                         # cookieconsent lib
        "#cookie-notice-accept-button",
        ".cookie-consent__btn--accept",
        "[data-testid='cookie-banner-accept']",
    ]
    for sel in vendor_selectors:
        try:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click()
                return
        except Exception:
            pass

    # Text-based fallback — scan first 30 buttons for known accept phrases
    accept_texts = {
        "alle akzeptieren", "alles akzeptieren", "alle cookies akzeptieren",
        "zustimmen", "akzeptieren", "einverstanden", "annehmen",
        "accept all", "accept all cookies", "accept cookies", "allow all",
        "i agree", "ich stimme zu",
    }
    try:
        buttons = await page.query_selector_all("button, a[role='button']")
        for btn in buttons[:30]:
            try:
                text = (await btn.inner_text()).strip().lower()
                if text in accept_texts and await btn.is_visible():
                    await btn.click()
                    return
            except Exception:
                pass
    except Exception:
        pass


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
            // CSS variables from :root
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


async def _extract_images(page) -> list[dict]:
    """Return up to 12 meaningful image src/alt pairs (after lazy-load scroll)."""
    imgs = await page.evaluate("""
        () => {
            const imgs = [...document.querySelectorAll('img')].filter(
                img => img.width > 80 && img.height > 80 && img.src && !img.src.startsWith('data:')
            );
            return imgs.slice(0, 12).map(img => ({
                src: img.src,
                alt: img.alt || '',
            }));
        }
    """)
    return imgs or []


async def _extract_bg_images(page) -> list[str]:
    """Extract CSS background-image URLs from computed styles (up to 8)."""
    urls = await page.evaluate("""
        () => {
            const seen = new Set();
            for (const el of document.querySelectorAll('*')) {
                const bg = getComputedStyle(el).backgroundImage;
                if (bg && bg !== 'none' && bg.includes('url(')) {
                    const m = bg.match(/url\\(["']?([^"')]+)["']?\\)/);
                    if (m && m[1].startsWith('http')) seen.add(m[1]);
                }
                if (seen.size >= 8) break;
            }
            return [...seen];
        }
    """)
    return urls or []


async def _analyze_design_patterns(page) -> dict:
    """Detect fonts, animation libs, transitions, and layout type of the current site."""
    try:
        return await page.evaluate("""
            () => {
                const fonts = [];
                try {
                    for (const f of document.fonts) {
                        if (f.status === 'loaded' && f.family)
                            fonts.push(f.family.replace(/['"]/g, '').trim());
                    }
                } catch(e) {}

                const libMap = {
                    gsap: typeof window.gsap !== 'undefined',
                    aos: typeof window.AOS !== 'undefined',
                    wow: typeof window.WOW !== 'undefined',
                    swiper: typeof window.Swiper !== 'undefined',
                    scrollReveal: typeof window.ScrollReveal !== 'undefined',
                    animateCSS: !!document.querySelector('.animate__animated'),
                };
                const animLibs = Object.keys(libMap).filter(k => libMap[k]);

                const transitions = new Set();
                for (const el of document.querySelectorAll('a,button,[class*="btn"],[class*="card"]')) {
                    const t = getComputedStyle(el).transition;
                    if (t && t !== 'all 0s ease 0s' && t !== 'none 0s ease 0s 0s')
                        transitions.add(t);
                    if (transitions.size >= 3) break;
                }

                let gridCount = 0, flexCount = 0;
                for (const el of document.querySelectorAll('section,main,article,.container,[class*="row"]')) {
                    const d = getComputedStyle(el).display;
                    if (d === 'grid' || d === 'inline-grid') gridCount++;
                    if (d === 'flex' || d === 'inline-flex') flexCount++;
                }

                const bodyBg = getComputedStyle(document.body).backgroundColor;
                const hasScrollAnim = animLibs.length > 0 || !!document.querySelector(
                    '[data-aos],[data-wow],[data-sal],[class*="fadein"],[class*="fade-in"],[class*="slide-up"]'
                );

                return {
                    fonts: [...new Set(fonts)].slice(0, 6),
                    animLibs,
                    hasScrollAnimations: hasScrollAnim,
                    hasTransitions: transitions.size > 0,
                    sampleTransitions: [...transitions].slice(0, 2),
                    layoutType: gridCount > flexCount ? 'grid-dominant' : 'flex-dominant',
                    bodyBg,
                };
            }
        """) or {}
    except Exception:
        return {}


async def scrape_website_content(url: str) -> dict:
    """
    Visit `url` and extract all content useful for demo generation.
    Returns a dict with keys: title, tagline, description, services, contact,
    colors, nav_items, testimonials, images, raw_text, subpage_text, screenshots.
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
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            )
            page = await ctx.new_page()
            await stealth_async(page)

            # Navigate — prefer networkidle (best for SPAs); fall back if it times out
            try:
                await page.goto(url, timeout=30000, wait_until="networkidle")
            except PWTimeout:
                # Partial load — continue if the page has any title/content
                if not await page.title():
                    return result
                # else: we likely have enough content; proceed

            # Dismiss cookie consent banners before extracting anything
            await _dismiss_cookie_banners(page)
            await asyncio.sleep(0.5)  # let the page settle after dismissal

            # Scroll to bottom and back to trigger lazy-load on images/content
            page_height = await page.evaluate("() => document.body.scrollHeight")
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(0.8)
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(0.5)

            # Resolve actual URL after any redirects (for correct subpage domain matching)
            from urllib.parse import urlparse, urlunparse
            actual_url = page.url
            actual_base = urlparse(actual_url).netloc or urlparse(url).netloc

            # Title
            result["title"] = await page.title() or ""

            # Nav items
            nav_links = await page.evaluate("""
                () => {
                    const nav = document.querySelector('nav') || document.querySelector('header');
                    if (!nav) return [];
                    return [...nav.querySelectorAll('a')]
                        .map(a => a.innerText.trim())
                        .filter(t => t.length > 0 && t.length < 40);
                }
            """)
            result["nav_items"] = list(dict.fromkeys(nav_links))[:8]

            # All visible text (increased cap to 15k chars)
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
                        .slice(0, 15000);
                }
            """)
            result["raw_text"] = raw or ""

            # Crawl internal subpages — skip legal/utility pages
            SKIP_KEYWORDS = ["impressum", "datenschutz", "privacy", "cookie", "agb", "widerruf",
                             "nutzungsbedingungen", "sitemap", "login", "cart", "warenkorb", "wp-admin"]
            all_links = await page.evaluate("""
                () => [...document.querySelectorAll('a[href]')]
                    .map(a => a.href)
                    .filter(h => h && !h.includes('#'))
            """)
            seen_paths = set()
            subpages_to_visit = []
            for link in all_links:
                try:
                    parsed = urlparse(link)
                    # Accept links on either the original or redirected domain
                    if parsed.netloc not in (actual_base, urlparse(url).netloc):
                        continue
                    path_lower = parsed.path.lower()
                    if any(kw in path_lower for kw in SKIP_KEYWORDS):
                        continue
                    clean = urlunparse(parsed._replace(query="", fragment=""))
                    if clean in (url, actual_url) or parsed.path in seen_paths or parsed.path == "/":
                        continue
                    seen_paths.add(parsed.path)
                    subpages_to_visit.append(clean)
                except Exception:
                    continue

            subpage_texts = []
            for sub_url in subpages_to_visit[:12]:
                try:
                    sub_page = await ctx.new_page()
                    try:
                        await sub_page.goto(sub_url, timeout=15000, wait_until="load")
                    except PWTimeout:
                        if not await sub_page.title():
                            await sub_page.close()
                            continue
                    sub_text = await sub_page.evaluate("""
                        () => {
                            const skip = new Set(['script','style','noscript','svg','path','nav','footer']);
                            function walk(el) {
                                if (skip.has(el.tagName?.toLowerCase())) return '';
                                if (el.nodeType === 3) return el.textContent;
                                return [...el.childNodes].map(walk).join(' ');
                            }
                            return walk(document.body).replace(/\\s+/g, ' ').trim().slice(0, 5000);
                        }
                    """)
                    if sub_text and len(sub_text.strip()) > 100:
                        subpage_texts.append(f"[{sub_url}]:\n{sub_text.strip()}")
                    await sub_page.close()
                except Exception:
                    pass

            if subpage_texts:
                result["subpage_text"] = "\n\n---\n\n".join(subpage_texts)

            # Headings
            headings = await page.evaluate("""
                () => [...document.querySelectorAll('h1,h2,h3')]
                    .map(h => h.innerText.trim())
                    .filter(t => t.length > 5 && t.length < 120)
                    .slice(0, 6)
            """)
            if headings:
                result["tagline"] = headings[0]
                result["description"] = " | ".join(headings[1:3]) if len(headings) > 1 else ""

            # Phone + email (heuristic — Sonnet extraction is the primary source)
            phone_match = re.search(r'[\+\(]?[\d\s\-\(\)]{7,20}', raw)
            if phone_match:
                result["contact"]["phone"] = phone_match.group().strip()
            email_match = re.search(r'[\w\.\-]+@[\w\.\-]+\.\w{2,}', raw)
            if email_match:
                result["contact"]["email"] = email_match.group()

            # Two screenshots: hero (0) + mid section (800px scroll)
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

            # Colors, images, CSS backgrounds, design analysis
            # (images extracted after lazy-load scroll above)
            result["colors"] = await _extract_colors(page)
            result["images"] = await _extract_images(page)
            result["bg_images"] = await _extract_bg_images(page)
            result["design_analysis"] = await _analyze_design_patterns(page)

            # Services heuristic
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

            # Testimonials heuristic
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
        print(f"[scraper] FAILED for {url}: {e}")

    return result
