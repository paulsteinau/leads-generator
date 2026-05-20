import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "leads.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url_hash TEXT UNIQUE NOT NULL,
    name TEXT, category TEXT, district TEXT, address TEXT,
    phone TEXT, email TEXT, website TEXT,
    google_rating REAL, google_reviews INTEGER,
    has_instagram INTEGER DEFAULT 0,
    has_facebook INTEGER DEFAULT 0,
    has_linkedin INTEGER DEFAULT 0,
    pagespeed_mobile INTEGER, pagespeed_desktop INTEGER,
    has_ssl INTEGER, cms_detected TEXT,
    has_cta INTEGER, has_booking INTEGER, is_mobile_ready INTEGER,
    seo_score INTEGER, red_flags TEXT DEFAULT '[]',
    lead_score INTEGER, lead_tier TEXT,
    stage TEXT DEFAULT 'scraped',
    email_subject TEXT, email_body_a TEXT, email_body_b TEXT,
    email_approved INTEGER DEFAULT 0, email_variant TEXT, email_sent_at TEXT,
    status TEXT DEFAULT 'new', notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS search_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT, district TEXT, category TEXT, results INTEGER,
    ran_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS email_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER REFERENCES leads(id),
    domain TEXT, sent_at TEXT, subject TEXT, body TEXT,
    reply TEXT, replied_at TEXT
);
CREATE TABLE IF NOT EXISTS cost_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd REAL,
    logged_at TEXT DEFAULT (datetime('now'))
);
"""


def get_conn(path=None):
    db_path = Path(path) if path else DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(path=None):
    conn = get_conn(path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn
