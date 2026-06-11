# pipeline/researcher/reference_screenshots.py
"""
Screenshots reference sites once per category and caches screenshot + CSS palette to disk.
Cache lives at DATA_DIR/ref_screenshots/<category>.json — never expires automatically.
Delete the file to force a refresh. Re-fetch also adds design_analysis (fonts, anim libs,
layout type) — delete cache files to pick this up for existing categories.
"""
import asyncio
import base64
import json
import os
from pathlib import Path

from playwright.async_api import async_playwright

from pipeline.researcher.inspiration import CATEGORY_REFERENCES
from pipeline.scraper.website_content import _analyze_design_patterns

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent.parent / "data"))
REF_CACHE_DIR = DATA_DIR / "ref_screenshots"


async def _fetch_reference(url: str) -> dict:
    """Navigate to url, take screenshots at multiple scroll positions, extract CSS palette."""
    result: dict = {"screenshots": [], "css": {}, "url": url}
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36",
            )
            await page.goto(f"https://{url}", timeout=30000, wait_until="domcontentloaded")
            await asyncio.sleep(2)

            # Get total page height
            page_height = await page.evaluate("() => document.body.scrollHeight")

            # Screenshots at viewport, mid, and lower section
            screenshots = []
            for scroll_y in [0, 800, 1600]:
                if scroll_y > 0 and scroll_y >= page_height:
                    break
                await page.evaluate(f"window.scrollTo(0, {scroll_y})")
                await asyncio.sleep(0.3)
                shot = await page.screenshot(type="jpeg", quality=75, full_page=False)
                screenshots.append(base64.b64encode(shot).decode())

            result["screenshots"] = screenshots

            # CSS palette: custom properties + computed styles on key elements
            css_data = await page.evaluate("""
                () => {
                    const root = getComputedStyle(document.documentElement);
                    const vars = {};
                    for (const prop of root) {
                        if (/--(?:color|primary|secondary|accent|bg|background|text|font)/i.test(prop)) {
                            const v = root.getPropertyValue(prop).trim();
                            if (v) vars[prop] = v;
                        }
                    }
                    const computed = {};
                    for (const sel of ['body', 'h1', 'h2', 'a', 'button', 'header', 'nav']) {
                        const el = document.querySelector(sel);
                        if (el) {
                            const s = getComputedStyle(el);
                            computed[sel] = {
                                color: s.color,
                                bg: s.backgroundColor,
                                font: s.fontFamily.split(',')[0].replace(/['"]/g, '').trim(),
                            };
                        }
                    }
                    return { vars, computed };
                }
            """)
            result["css"] = css_data or {}

            # Design pattern analysis — same function used for lead's current site
            result["design_analysis"] = await _analyze_design_patterns(page)

            await browser.close()
    except Exception as e:
        result["error"] = str(e)
    return result


def _get_site_cache_file(category: str, idx: int) -> Path:
    return REF_CACHE_DIR / f"{category}_{idx}.json"


def _fetch_and_cache_site(category: str, url: str, idx: int) -> dict:
    """Fetch one reference site and cache it. Returns data dict."""
    cache_file = _get_site_cache_file(category, idx)
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    print(f"[ref_screenshots] Fetching {category}[{idx}]: {url}")
    data = asyncio.run(_fetch_reference(url))

    if data.get("screenshots"):
        cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        print(f"[ref_screenshots] Cached {category}[{idx}] ({len(data['screenshots'])} shots)")
    else:
        print(f"[ref_screenshots] Failed {url}: {data.get('error', 'unknown')}")

    return data


def get_all_reference_data(category: str) -> list[dict]:
    """
    Returns cached data for all reference sites of a category.
    Runs Playwright on first call per site, then uses cache.
    Each site gets its own cache file: {category}_{idx}.json
    """
    REF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    refs = CATEGORY_REFERENCES.get(category, [])
    results = []
    for idx, url in enumerate(refs):
        data = _fetch_and_cache_site(category, url, idx)
        if data.get("screenshots"):
            results.append(data)
    return results
