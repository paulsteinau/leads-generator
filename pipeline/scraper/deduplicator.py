import hashlib


def url_hash(url: str) -> str:
    return hashlib.md5(url.strip().lower().encode()).hexdigest()


def is_duplicate(conn, url: str) -> bool:
    h = url_hash(url)
    return conn.execute(
        "SELECT 1 FROM leads WHERE url_hash=?", (h,)
    ).fetchone() is not None
