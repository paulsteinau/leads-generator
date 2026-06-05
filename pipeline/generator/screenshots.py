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
