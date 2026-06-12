import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent / "data")) / "leads.db"

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
    email_subjects TEXT,
    email_approved INTEGER DEFAULT 0, email_variant TEXT, email_sent_at TEXT,
    email_message_id TEXT,
    status TEXT DEFAULT 'new', notes TEXT,
    description TEXT,
    description_data TEXT,
    industry_tag TEXT,
    audit_score INTEGER,
    audit_data TEXT,
    qualification TEXT,
    demo_url TEXT,
    demo_generated_at TEXT,
    demo_screenshots TEXT,
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
    model TEXT,
    stage TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd REAL,
    logged_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS industry_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    industry_tag TEXT UNIQUE NOT NULL,
    pattern_data TEXT NOT NULL,
    researched_at TEXT DEFAULT (datetime('now')),
    expires_at TEXT
);
CREATE TABLE IF NOT EXISTS suppressions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE,
    domain TEXT,
    reason TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS admin_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER REFERENCES leads(id),
    action TEXT,
    payload TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_leads_stage ON leads(stage);
CREATE INDEX IF NOT EXISTS idx_leads_tier ON leads(lead_tier);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_industry ON leads(industry_tag);
CREATE INDEX IF NOT EXISTS idx_leads_qualification ON leads(qualification);
CREATE INDEX IF NOT EXISTS idx_email_log_domain ON email_log(domain, sent_at);
CREATE INDEX IF NOT EXISTS idx_suppressions_email ON suppressions(email);
CREATE INDEX IF NOT EXISTS idx_suppressions_domain ON suppressions(domain);
CREATE INDEX IF NOT EXISTS idx_leads_email_msg ON leads(email_message_id);
"""


def _apply_migrations(conn) -> None:
    """Idempotent ALTER TABLE migrations for schema evolution."""
    migrations = [
        # cost_log: CLI-based logging (model + stage replace token counters)
        "ALTER TABLE cost_log ADD COLUMN model TEXT",
        "ALTER TABLE cost_log ADD COLUMN stage TEXT",
        # leads: enrichment + audit + demo columns
        "ALTER TABLE leads ADD COLUMN description TEXT",
        "ALTER TABLE leads ADD COLUMN description_data TEXT",
        "ALTER TABLE leads ADD COLUMN industry_tag TEXT",
        "ALTER TABLE leads ADD COLUMN audit_score INTEGER",
        "ALTER TABLE leads ADD COLUMN audit_data TEXT",
        "ALTER TABLE leads ADD COLUMN qualification TEXT",
        "ALTER TABLE leads ADD COLUMN demo_url TEXT",
        "ALTER TABLE leads ADD COLUMN demo_generated_at TEXT",
        "ALTER TABLE leads ADD COLUMN demo_screenshots TEXT",
        "ALTER TABLE leads ADD COLUMN email_subjects TEXT",
        "ALTER TABLE leads ADD COLUMN email_message_id TEXT",
        "ALTER TABLE leads ADD COLUMN demo_sub_stage TEXT",
        # cost_log: accurate per-generation tracking + cache tokens
        "ALTER TABLE cost_log ADD COLUMN cache_read_tokens INTEGER DEFAULT 0",
        "ALTER TABLE cost_log ADD COLUMN cache_write_tokens INTEGER DEFAULT 0",
        "ALTER TABLE cost_log ADD COLUMN generation_num INTEGER DEFAULT 1",
        # demo source stored in DB so it can be retrieved/edited without Railway filesystem
        "ALTER TABLE leads ADD COLUMN demo_jsx TEXT",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
        except Exception:
            pass  # column already exists
    conn.commit()


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
    _apply_migrations(conn)
    return conn
