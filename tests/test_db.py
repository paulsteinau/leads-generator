import sqlite3
from api.db import init_db, get_conn


def test_init_creates_tables(tmp_path):
    conn = init_db(path=str(tmp_path / "test.db"))
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "leads" in tables
    assert "search_runs" in tables
    assert "email_log" in tables


def test_wal_mode(tmp_path):
    init_db(path=str(tmp_path / "test.db"))
    conn = get_conn(path=str(tmp_path / "test.db"))
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"


def test_lead_defaults(tmp_path):
    conn = init_db(path=str(tmp_path / "test.db"))
    conn.execute("INSERT INTO leads (url_hash, name) VALUES (?,?)", ("abc", "Test GmbH"))
    conn.commit()
    row = conn.execute("SELECT * FROM leads WHERE url_hash='abc'").fetchone()
    assert row["stage"] == "scraped"
    assert row["status"] == "new"
    assert row["red_flags"] == "[]"
