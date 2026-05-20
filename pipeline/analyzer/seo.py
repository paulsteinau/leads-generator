import httpx
from bs4 import BeautifulSoup

CMS_SIGS = {
    "wix": ["wix.com", "wixsite.com", "_wix_"],
    "jimdo": ["jimdo.com", "jimdofree.com"],
    "squarespace": ["squarespace.com", "squarespace-cdn.com"],
    "wordpress": ["wp-content", "wp-includes"],
    "shopify": ["cdn.shopify.com"],
}
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def analyze_seo(website: str, timeout: int = 10) -> dict:
    result = {
        "has_ssl": website.startswith("https://"),
        "seo_score": 0,
        "cms_detected": None,
        "red_flags": [],
    }
    try:
        resp = httpx.get(website, timeout=timeout, follow_redirects=True, headers=HEADERS)
        soup = BeautifulSoup(resp.text, "html.parser")
        html = resp.text.lower()
        score = 0

        title = soup.find("title")
        if title and title.text.strip():
            score += 20
        else:
            result["red_flags"].append("no_title")

        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content", "").strip():
            score += 20
        else:
            result["red_flags"].append("no_meta")

        h1 = soup.find("h1")
        if h1 and h1.text.strip():
            score += 20
        else:
            result["red_flags"].append("no_h1")

        for sub_path, flag in [("/robots.txt", "no_robots"), ("/sitemap.xml", "no_sitemap")]:
            try:
                r = httpx.get(website.rstrip("/") + sub_path, timeout=5, headers=HEADERS)
                if r.status_code == 200:
                    score += 20
                else:
                    result["red_flags"].append(flag)
            except Exception:
                result["red_flags"].append(flag)

        result["seo_score"] = score

        for cms, sigs in CMS_SIGS.items():
            if any(s in html for s in sigs):
                result["cms_detected"] = cms
                if cms in ("wix", "jimdo", "squarespace"):
                    result["red_flags"].append(f"{cms}_site")
                break

        if not result["has_ssl"]:
            result["red_flags"].append("no_ssl")

    except Exception:
        result["red_flags"].append("site_unreachable")

    return result
