import hashlib
from urllib.parse import urlparse


def _normalize(url: str) -> str:
    url = url.strip().lower()
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = parsed.netloc or parsed.path
    host = host.removeprefix("www.")
    path = parsed.path.rstrip("/")
    return f"{host}{path}"


def url_hash(url: str) -> str:
    return hashlib.md5(_normalize(url).encode()).hexdigest()


def is_duplicate(conn, url: str) -> bool:
    h = url_hash(url)
    return conn.execute(
        "SELECT 1 FROM leads WHERE url_hash=?", (h,)
    ).fetchone() is not None
