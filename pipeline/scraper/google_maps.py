import asyncio
import random
import re
from playwright.async_api import async_playwright
try:
    from playwright_stealth import stealth_async
except Exception:
    async def stealth_async(page): pass

UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]


async def _accept_cookies(page):
    for sel in [
        'button[jsname="b3VHJd"]',
        'button[jsname="higCR"]',
        'button[aria-label*="Alle ablehnen"]',
        'button[aria-label*="Reject all"]',
        'button[aria-label*="Accept all"]',
        'button[aria-label*="Alle akzeptieren"]',
        'form[action*="consent"] button',
        '#L2AGLb',
    ]:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=2000):
                await btn.click()
                await asyncio.sleep(1.5)
                return
        except Exception:
            continue


async def scrape_google_maps(query: str, max_results: int = 15) -> list[dict]:
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--window-position=-32000,-32000",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        ctx = await browser.new_context(
            user_agent=random.choice(UAS),
            locale="de-DE",
            viewport={"width": 1280, "height": 800},
        )
        page = await ctx.new_page()
        await stealth_async(page)

        url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            await browser.close()
            return []

        await asyncio.sleep(random.uniform(2, 3))
        await _accept_cookies(page)
        await asyncio.sleep(random.uniform(1, 2))

        # Find results feed
        feed_sel = None
        for sel in ['[role="feed"]', '.m6QErb[aria-label]', '.DxyBCb']:
            try:
                await page.wait_for_selector(sel, timeout=10000)
                feed_sel = sel
                break
            except Exception:
                continue

        if not feed_sel:
            await browser.close()
            return []

        # Scroll via page.evaluate (avoids locator timeout on detached elements)
        for _ in range(3):
            try:
                await page.evaluate(
                    f"const f = document.querySelector('{feed_sel}'); if(f) f.scrollTop += 800;"
                )
                await asyncio.sleep(random.uniform(1, 1.5))
            except Exception:
                break

        # Extract result cards
        cards = await page.query_selector_all('.Nv2PK')
        if not cards:
            cards = await page.query_selector_all('[jsaction*="mouseover:pane"]')

        for card in cards[:max_results]:
            try:
                await card.click()
                await asyncio.sleep(random.uniform(1.5, 2.5))

                async def txt(sel):
                    try:
                        el = await page.query_selector(sel)
                        return (await el.inner_text()).strip() if el else None
                    except Exception:
                        return None

                async def attr(sel, a):
                    try:
                        el = await page.query_selector(sel)
                        return await el.get_attribute(a) if el else None
                    except Exception:
                        return None

                name = await txt('h1.DUwDvf') or await txt('h1')
                address = await txt('[data-item-id="address"] .Io6YTe')
                rating_el = await page.query_selector('.F7nice span[aria-hidden]')
                rating = None
                if rating_el:
                    try:
                        rating = float((await rating_el.inner_text()).replace(",", "."))
                    except Exception:
                        pass
                rev_el = await page.query_selector('.F7nice span[aria-label]')
                rev_text = await rev_el.get_attribute("aria-label") if rev_el else ""
                reviews = _parse_reviews(rev_text or "")
                website = await attr('a[data-item-id="authority"]', "href")
                phone = await txt('[data-item-id^="phone"] .Io6YTe')

                if name:
                    results.append({
                        "name": name,
                        "address": address,
                        "google_rating": rating,
                        "google_reviews": reviews,
                        "website": website or None,
                        "phone": phone,
                    })
            except Exception:
                continue

        await browser.close()
    return results


def _parse_reviews(text: str) -> int | None:
    cleaned = text.replace(".", "").replace(",", "").replace("\xa0", "")
    m = re.search(r'(\d+)', cleaned)
    return int(m.group(1)) if m else None
