import asyncio
import re
import httpx

OBFUSCATION = [
    (r'\s*\[at\]\s*', '@'),
    (r'\s*\(at\)\s*', '@'),
    (r'\s+AT\s+', '@'),
    (r'\s*\[dot\]\s*', '.'),
    (r'\s*\(dot\)\s*', '.'),
]
EMAIL_RE = r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}'
PHONE_RE = r'(\+49[\s\-]?\d[\d\s\-]{7,}|\(0\d{2,4}\)\s?[\d\s\-]{4,}|0\d{2,4}[\s\/\-]?[\d\s\-]{4,})'
BAD_EXT = {'.png', '.jpg', '.gif', '.svg', '.css', '.js', '.woff', '.ico'}


def _deobfuscate(text: str) -> str:
    for pat, rep in OBFUSCATION:
        text = re.sub(pat, rep, text, flags=re.IGNORECASE)
    return text


def _extract_email_from_text(text: str) -> str | None:
    cleaned = _deobfuscate(text)
    matches = [m for m in re.findall(EMAIL_RE, cleaned)
               if not any(m.lower().endswith(e) for e in BAD_EXT)]
    return matches[0] if matches else None


def _extract_phone_from_text(text: str) -> str | None:
    matches = re.findall(PHONE_RE, text)
    if not matches:
        return None
    m = matches[0]
    return (m if isinstance(m, str) else m[0]).strip()


async def _extract_one(website: str, timeout: int = 10) -> dict:
    result: dict = {"email": None, "phone": None}
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        ) as client:
            for path in ["/impressum", "/kontakt", "/contact", "/"]:
                try:
                    resp = await client.get(website.rstrip("/") + path)
                    if resp.status_code != 200:
                        continue
                    text = resp.text
                    if not result["email"]:
                        result["email"] = _extract_email_from_text(text)
                    if not result["phone"]:
                        result["phone"] = _extract_phone_from_text(text)
                    if result["email"] and result["phone"]:
                        break
                except Exception:
                    continue
    except Exception:
        pass
    return result


async def extract_contacts_batch(leads: list[dict], max_concurrent: int = 10) -> dict[int, dict]:
    sem = asyncio.Semaphore(max_concurrent)

    async def one(lead: dict) -> tuple[int, dict]:
        async with sem:
            if lead.get("website"):
                contacts = await _extract_one(lead["website"])
            else:
                contacts = {"email": None, "phone": None}
        return lead["id"], contacts

    pairs = await asyncio.gather(*[one(l) for l in leads], return_exceptions=True)
    out: dict[int, dict] = {}
    for lead, res in zip(leads, pairs):
        if isinstance(res, tuple):
            out[res[0]] = res[1]
        else:
            out[lead["id"]] = {"email": None, "phone": None}
    return out


def extract_contacts(website: str, timeout: int = 10) -> dict:
    return asyncio.run(_extract_one(website, timeout))
