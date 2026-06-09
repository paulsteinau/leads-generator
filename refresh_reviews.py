"""
Aktualisiert google_reviews fuer alle Leads in der DB.
Sucht jeden Lead einzeln auf Google Maps und liest die Anzahl aus dem ersten Treffer.
Laufzeit: ~10-15 Minuten fuer alle Leads.
"""
import asyncio
import random
import re
import sqlite3

from playwright.async_api import async_playwright
try:
    from playwright_stealth import stealth_async
except Exception:
    async def stealth_async(p): pass

DB_PATH = "data/leads.db"


def _parse_reviews(text: str) -> int | None:
    cleaned = text.replace(".", "").replace(",", "").replace("\xa0", "")
    m = re.search(r'(\d+)', cleaned)
    return int(m.group(1)) if m else None


async def _get_count(page, name: str, district: str) -> int | None:
    query = f"{name} {district}".replace(" ", "+")
    try:
        await page.goto(
            f"https://www.google.com/maps/search/{query}",
            wait_until="domcontentloaded", timeout=30000,
        )
        await asyncio.sleep(random.uniform(2, 3))

        # Alle span[aria-label] auf der gesamten Seite durchsuchen
        # Funktioniert sowohl bei Listenansicht als auch Detail-Panel
        for span in await page.query_selector_all('span[aria-label]'):
            label = await span.get_attribute("aria-label") or ""
            if any(w in label.lower() for w in ["rezension", "review", "bewertung"]):
                count = _parse_reviews(label)
                if count is not None and count > 0:
                    return count
    except Exception as e:
        print(f"    Fehler: {e}")
    return None


async def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    leads = conn.execute(
        "SELECT id, name, district, google_reviews FROM leads WHERE name IS NOT NULL ORDER BY id"
    ).fetchall()
    print(f"{len(leads)} Leads werden aktualisiert...\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--window-position=-32000,-32000", "--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
            locale="de-DE",
            viewport={"width": 1280, "height": 800},
        )
        page = await ctx.new_page()
        await stealth_async(page)

        # Cookies einmal akzeptieren
        await page.goto("https://www.google.com/maps", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        for sel in ['button[jsname="b3VHJd"]', 'button[jsname="higCR"]', '#L2AGLb',
                    'button[aria-label*="Alle ablehnen"]', 'form[action*="consent"] button']:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    await asyncio.sleep(1)
                    break
            except Exception:
                continue

        updated = 0
        for i, lead in enumerate(leads, 1):
            count = await _get_count(page, lead["name"], lead["district"] or "Berlin")
            old = lead["google_reviews"]
            if count is not None and count != old:
                conn.execute("UPDATE leads SET google_reviews=?, updated_at=datetime('now') WHERE id=?",
                             (count, lead["id"]))
                conn.commit()
                print(f"[{i}/{len(leads)}] {lead['name']}: {old} -> {count} ✓")
                updated += 1
            else:
                status = f"{old} (unveraendert)" if count == old else "nicht gefunden"
                print(f"[{i}/{len(leads)}] {lead['name']}: {status}")
            await asyncio.sleep(random.uniform(1.5, 2.5))

        await browser.close()

    print(f"\nFertig! {updated} von {len(leads)} Leads aktualisiert.")


asyncio.run(main())
