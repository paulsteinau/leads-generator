import httpx

SOCIALS = {
    "has_instagram": ["instagram.com/", "instagr.am/"],
    "has_facebook": ["facebook.com/", "fb.com/"],
    "has_linkedin": ["linkedin.com/company/", "linkedin.com/in/"],
}


def analyze_social(website: str, timeout: int = 10) -> dict:
    result = {"has_instagram": False, "has_facebook": False, "has_linkedin": False}
    try:
        resp = httpx.get(
            website, timeout=timeout, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        html = resp.text.lower()
        for key, patterns in SOCIALS.items():
            result[key] = any(p in html for p in patterns)
    except Exception:
        pass
    return result
