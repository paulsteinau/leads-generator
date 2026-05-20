import asyncio
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
try:
    from playwright_stealth import stealth_async
except Exception:
    async def stealth_async(page): pass

CTA_KW = ["termin", "buchen", "kontakt", "anfrage", "reservier", "jetzt starten"]
BOOKING_KW = ["online buchen", "termin buchen", "calendly", "booking", "appointlet"]


async def analyze_ux_batch(urls: list[str], max_concurrent: int = 5) -> dict[str, dict]:
    sem = asyncio.Semaphore(max_concurrent)
    results: dict[str, dict] = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        async def _check_one(url: str) -> dict:
            result = {"has_cta": False, "has_booking": False, "is_mobile_ready": False, "red_flags": []}
            async with sem:
                ctx = await browser.new_context(
                    viewport={"width": 375, "height": 812},
                    user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0)",
                )
                try:
                    page = await ctx.new_page()
                    await stealth_async(page)
                    await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    html = (await page.content()).lower()

                    result["has_cta"] = any(k in html for k in CTA_KW)
                    result["has_booking"] = any(k in html for k in BOOKING_KW)
                    result["is_mobile_ready"] = (
                        await page.query_selector('meta[name="viewport"]') is not None
                    )

                    if not result["has_cta"]:
                        result["red_flags"].append("no_cta")
                    if not result["has_booking"]:
                        result["red_flags"].append("no_booking")
                    if not result["is_mobile_ready"]:
                        result["red_flags"].append("no_mobile")
                except PWTimeout:
                    result["red_flags"].append("ux_check_timeout")
                except Exception:
                    result["red_flags"].append("ux_check_timeout")
                finally:
                    await ctx.close()
            return result

        tasks = [_check_one(url) for url in urls]
        values = await asyncio.gather(*tasks, return_exceptions=True)
        await browser.close()

    for url, val in zip(urls, values):
        if isinstance(val, dict):
            results[url] = val
        else:
            results[url] = {"has_cta": False, "has_booking": False, "is_mobile_ready": False, "red_flags": ["ux_check_timeout"]}
    return results
