import asyncio
import os
import httpx

PAGESPEED_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


async def _fetch(client: httpx.AsyncClient, url: str, strategy: str) -> int | None:
    try:
        r = await client.get(
            PAGESPEED_URL, timeout=30,
            params={"url": url, "strategy": strategy,
                    "key": os.environ.get("GOOGLE_API_KEY", "")},
        )
        score = (r.json()
                 .get("lighthouseResult", {})
                 .get("categories", {})
                 .get("performance", {})
                 .get("score"))
        return int(score * 100) if score is not None else None
    except Exception:
        return None


async def analyze_pagespeed_batch(urls: list[str], max_concurrent: int = 2) -> dict[str, dict]:
    results: dict[str, dict] = {}
    sem = asyncio.Semaphore(max_concurrent)

    async def one(url: str):
        async with sem:
            async with httpx.AsyncClient() as client:
                mobile = await _fetch(client, url, "mobile")
                await asyncio.sleep(1)
                desktop = await _fetch(client, url, "desktop")
                await asyncio.sleep(1)
        flags = []
        if mobile is not None and mobile < 50:
            flags.append("slow_mobile")
        if desktop is not None and desktop < 50:
            flags.append("slow_desktop")
        results[url] = {"pagespeed_mobile": mobile, "pagespeed_desktop": desktop, "red_flags": flags}

    await asyncio.gather(*[one(u) for u in urls])
    return results
