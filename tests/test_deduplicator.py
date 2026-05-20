from pipeline.scraper.deduplicator import url_hash, is_duplicate
from api.db import init_db


def test_url_hash_deterministic():
    assert url_hash("https://example.com") == url_hash("https://example.com")


def test_url_hash_normalizes():
    assert url_hash("  HTTPS://Example.COM  ") == url_hash("https://example.com")


def test_is_duplicate_false_when_missing(tmp_path):
    conn = init_db(path=str(tmp_path / "test.db"))
    assert is_duplicate(conn, "https://new-site.de") is False


def test_is_duplicate_true_when_present(tmp_path):
    conn = init_db(path=str(tmp_path / "test.db"))
    url = "https://zahnarzt-mitte.de"
    h = url_hash(url)
    conn.execute("INSERT INTO leads (url_hash, name) VALUES (?,?)", (h, "Test"))
    conn.commit()
    assert is_duplicate(conn, url) is True
