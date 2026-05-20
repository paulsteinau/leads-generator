# Berlin Lead-Gen System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Python pipeline that finds Berlin businesses with weak online presence, scores them, generates personalized German outreach emails via Claude Haiku, and presents everything in a Next.js dashboard with manual email approval via mailto: links.

**Architecture:** Modular Python pipeline (scraper → analyzer → extractor → scorer → emailgen) writes to SQLite (WAL mode). FastAPI serves 6 endpoints to a Next.js dashboard on localhost:3000. Email sends use mailto: links — never automatic.

**Tech Stack:** Python 3.12, Playwright + playwright-stealth, httpx, beautifulsoup4, anthropic SDK, FastAPI, uvicorn, SQLite, Next.js 14, Tailwind CSS, pytest

---

## File Map

| File | Responsibility |
|---|---|
| `requirements.txt` | Python deps |
| `.env.example` | API key template |
| `.gitignore` | Ignores data/, .env, __pycache__ |
| `api/db.py` | SQLite init, WAL, schema |
| `api/models.py` | Pydantic schemas |
| `api/main.py` | FastAPI, 6 endpoints, CORS |
| `pipeline/scraper/search_queries.py` | Branche×Bezirk matrix, daily rotation |
| `pipeline/scraper/deduplicator.py` | MD5 hash, duplicate check |
| `pipeline/scraper/google_maps.py` | Playwright+stealth Google Maps |
| `pipeline/analyzer/seo.py` | httpx SEO + CMS detection |
| `pipeline/analyzer/social.py` | Social link detection |
| `pipeline/analyzer/website.py` | PageSpeed Insights async |
| `pipeline/analyzer/ux.py` | Playwright UX check, 30s timeout |
| `pipeline/extractor/contact.py` | Email/phone, obfuscation handling |
| `pipeline/scorer/engine.py` | Weighted scoring, penalties, tiers |
| `pipeline/emailgen/generator.py` | Claude Haiku, 2 DE variants, cooldown |
| `pipeline/run.py` | Orchestrator, tqdm, logging, --dry-run |
| `dashboard/src/lib/api.ts` | Typed fetch functions |
| `dashboard/src/app/page.tsx` | Stats bar + filters + lead table |
| `dashboard/src/app/leads/[id]/page.tsx` | Lead detail (server) |
| `dashboard/src/app/leads/[id]/EmailPanel.tsx` | Email review + mailto (client) |
| `tests/test_db.py` | Schema, WAL |
| `tests/test_search_queries.py` | Matrix, rotation |
| `tests/test_deduplicator.py` | Hash, duplicate |
| `tests/test_scorer.py` | Scoring rules, tiers |
| `tests/test_extractor.py` | Regex, obfuscation, phone |
| `tests/test_models.py` | Pydantic validation |
| `scripts/run_pipeline.bat` | Run pipeline (Windows) |
| `scripts/run_dry.bat` | Dry run (Windows) |
| `scripts/start_api.bat` | Start FastAPI (Windows) |
| `scripts/start_dashboard.bat` | Start Next.js (Windows) |

---

## Task 1: Project Setup

**Files:** `requirements.txt`, `.env.example`, `.gitignore`, all `__init__.py`

- [ ] **Step 1: Create requirements.txt**

```
playwright==1.44.0
playwright-stealth==1.0.6
httpx==0.27.0
beautifulsoup4==4.12.3
anthropic==0.28.0
fastapi==0.111.0
uvicorn[standard]==0.29.0
pydantic==2.7.1
tqdm==4.66.4
python-dotenv==1.0.1
pytest==8.2.0
```

- [ ] **Step 2: Create .env.example**

```
ANTHROPIC_API_KEY=sk-ant-your-key-here
GOOGLE_API_KEY=AIzaSy-your-key-here
```

- [ ] **Step 3: Create .gitignore**

```
data/
.env
__pycache__/
*.pyc
.pytest_cache/
pipeline.log
dashboard/node_modules/
dashboard/.next/
```

- [ ] **Step 4: Create empty __init__.py files**

Create at: `pipeline/__init__.py`, `pipeline/scraper/__init__.py`, `pipeline/analyzer/__init__.py`, `pipeline/extractor/__init__.py`, `pipeline/scorer/__init__.py`, `pipeline/emailgen/__init__.py`, `api/__init__.py`, `tests/__init__.py`

- [ ] **Step 5: Install and setup**

```
pip install -r requirements.txt
playwright install chromium
copy .env.example .env
```

Fill in `.env` with your actual API keys.

- [ ] **Step 6: Commit**

```
git init
git add .
git commit -m "chore: project setup"
```

---

## Task 2: Database Layer

**Files:** `api/db.py`, `tests/test_db.py`

- [ ] **Step 1: Write failing tests**

`tests/test_db.py`:
```python
import sqlite3
import pytest
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
```

- [ ] **Step 2: Run — expect ImportError**

```
pytest tests/test_db.py -v
```

- [ ] **Step 3: Implement api/db.py**

```python
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
```

- [ ] **Step 4: Run — expect 3 passed**

```
pytest tests/test_db.py -v
```

- [ ] **Step 5: Commit**

```
git add api/db.py tests/test_db.py
git commit -m "feat: SQLite database layer with WAL mode"
```

---

## Task 3: Pydantic Models + FastAPI Skeleton

**Files:** `api/models.py`, `api/main.py`, `tests/test_models.py`

- [ ] **Step 1: Write failing tests**

`tests/test_models.py`:
```python
from api.models import LeadSummary, StatsResponse

def test_lead_summary():
    lead = LeadSummary(
        id=1, name="Test", category="Zahnarzt", district="Mitte",
        lead_score=14, lead_tier="hot", stage="scored", status="new",
        has_email=True, follow_up_due=False, created_at="2026-05-19"
    )
    assert lead.lead_tier == "hot"

def test_stats():
    s = StatsResponse(hot=5, warm=12, low=30, new_today=10, contacted=3, replied=1)
    assert s.hot == 5
```

- [ ] **Step 2: Run — expect ImportError**

```
pytest tests/test_models.py -v
```

- [ ] **Step 3: Implement api/models.py**

```python
from pydantic import BaseModel
from typing import Optional

class LeadSummary(BaseModel):
    id: int
    name: Optional[str] = None
    category: Optional[str] = None
    district: Optional[str] = None
    lead_score: Optional[int] = None
    lead_tier: Optional[str] = None
    stage: str
    status: str
    has_email: bool
    follow_up_due: bool
    created_at: str

class LeadDetail(BaseModel):
    id: int
    name: Optional[str] = None
    category: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    google_rating: Optional[float] = None
    google_reviews: Optional[int] = None
    has_instagram: bool = False
    has_facebook: bool = False
    has_linkedin: bool = False
    pagespeed_mobile: Optional[int] = None
    pagespeed_desktop: Optional[int] = None
    has_ssl: Optional[bool] = None
    cms_detected: Optional[str] = None
    has_cta: Optional[bool] = None
    has_booking: Optional[bool] = None
    is_mobile_ready: Optional[bool] = None
    seo_score: Optional[int] = None
    red_flags: list[str] = []
    lead_score: Optional[int] = None
    lead_tier: Optional[str] = None
    stage: str
    email_subject: Optional[str] = None
    email_body_a: Optional[str] = None
    email_body_b: Optional[str] = None
    email_approved: bool = False
    email_variant: Optional[str] = None
    status: str
    notes: Optional[str] = None
    created_at: str
    updated_at: str

class StatsResponse(BaseModel):
    hot: int; warm: int; low: int
    new_today: int; contacted: int; replied: int

class ApproveEmailRequest(BaseModel):
    variant: str  # "a" or "b"

class UpdateStatusRequest(BaseModel):
    status: str
```

- [ ] **Step 4: Implement api/main.py**

```python
import json, csv, io
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from api.db import get_conn, init_db
from api.models import (LeadSummary, LeadDetail, StatsResponse,
                         ApproveEmailRequest, UpdateStatusRequest)

app = FastAPI(title="Berlin Lead-Gen API")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"],
                   allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def startup(): init_db()

@app.get("/stats", response_model=StatsResponse)
def get_stats():
    conn = get_conn()
    today = datetime.now().strftime("%Y-%m-%d")
    def count(q, *p): return conn.execute(q, p).fetchone()[0]
    return StatsResponse(
        hot=count("SELECT COUNT(*) FROM leads WHERE lead_tier='hot'"),
        warm=count("SELECT COUNT(*) FROM leads WHERE lead_tier='warm'"),
        low=count("SELECT COUNT(*) FROM leads WHERE lead_tier='low'"),
        new_today=count("SELECT COUNT(*) FROM leads WHERE created_at >= ?", today),
        contacted=count("SELECT COUNT(*) FROM leads WHERE status='contacted'"),
        replied=count("SELECT COUNT(*) FROM leads WHERE status='replied'"),
    )

@app.get("/leads")
def list_leads(tier: str | None = None, district: str | None = None,
               category: str | None = None, stage: str | None = None) -> list[LeadSummary]:
    conn = get_conn()
    q = "SELECT * FROM leads WHERE 1=1"
    p: list = []
    for col, val in [("lead_tier", tier), ("district", district),
                     ("category", category), ("stage", stage)]:
        if val:
            q += f" AND {col}=?"; p.append(val)
    q += " ORDER BY lead_score DESC"
    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    return [LeadSummary(
        id=r["id"], name=r["name"], category=r["category"], district=r["district"],
        lead_score=r["lead_score"], lead_tier=r["lead_tier"],
        stage=r["stage"], status=r["status"], has_email=bool(r["email"]),
        follow_up_due=(r["status"] == "contacted" and (r["updated_at"] or "") < cutoff),
        created_at=r["created_at"] or "",
    ) for r in conn.execute(q, p).fetchall()]

@app.get("/leads/export")
def export_leads(tier: str | None = None):
    conn = get_conn()
    q = "SELECT * FROM leads" + (" WHERE lead_tier=?" if tier else "")
    rows = conn.execute(q, [tier] if tier else []).fetchall()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["id","name","category","district","email","phone","website",
                "lead_score","lead_tier","status","created_at"])
    for r in rows:
        w.writerow([r["id"],r["name"],r["category"],r["district"],r["email"],
                    r["phone"],r["website"],r["lead_score"],r["lead_tier"],
                    r["status"],r["created_at"]])
    out.seek(0)
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"})

@app.get("/leads/{lead_id}", response_model=LeadDetail)
def get_lead(lead_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    if not row: raise HTTPException(404, "Lead not found")
    d = dict(row)
    d["red_flags"] = json.loads(d.get("red_flags") or "[]")
    for k in ["has_instagram","has_facebook","has_linkedin","email_approved"]:
        d[k] = bool(d.get(k))
    for k in ["has_ssl","has_cta","has_booking","is_mobile_ready"]:
        d[k] = bool(d[k]) if d.get(k) is not None else None
    d["updated_at"] = d.get("updated_at") or ""
    return LeadDetail(**d)

@app.post("/leads/{lead_id}/approve-email")
def approve_email(lead_id: int, body: ApproveEmailRequest):
    if body.variant not in ("a", "b"):
        raise HTTPException(400, "variant must be 'a' or 'b'")
    conn = get_conn()
    conn.execute("UPDATE leads SET email_approved=1, email_variant=?, status='contacted',"
                 " updated_at=datetime('now') WHERE id=?", (body.variant, lead_id))
    conn.commit()
    return {"ok": True}

@app.post("/leads/{lead_id}/status")
def update_status(lead_id: int, body: UpdateStatusRequest):
    allowed = {"contacted","replied","closed","ignored","new"}
    if body.status not in allowed:
        raise HTTPException(400, f"status must be one of {allowed}")
    conn = get_conn()
    conn.execute("UPDATE leads SET status=?, updated_at=datetime('now') WHERE id=?",
                 (body.status, lead_id))
    conn.commit()
    return {"ok": True}
```

- [ ] **Step 5: Run model tests**

```
pytest tests/test_models.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Start API and verify**

```
uvicorn api.main:app --reload --port 8000
```

Visit `http://localhost:8000/docs` — Swagger UI should show all 6 endpoints.

- [ ] **Step 7: Commit**

```
git add api/models.py api/main.py tests/test_models.py
git commit -m "feat: Pydantic models and complete FastAPI with all 6 endpoints"
```

---

## Task 4: Search Queries + Deduplicator

**Files:** `pipeline/scraper/search_queries.py`, `pipeline/scraper/deduplicator.py`, tests

- [ ] **Step 1: Write failing tests**

`tests/test_search_queries.py`:
```python
from pipeline.scraper.search_queries import all_queries, get_daily_queries
from api.db import init_db

def test_all_queries_count():
    assert len(all_queries()) == 110  # 11 × 10

def test_query_has_required_keys():
    q = all_queries()[0]
    assert {"query", "category", "district"} <= q.keys()

def test_high_roi_first():
    q = all_queries()
    assert q[0]["category"] in {"Zahnarzt", "Anwalt", "Immobilienmakler"}

def test_get_daily_returns_n(tmp_path):
    conn = init_db(path=str(tmp_path / "t.db"))
    assert len(get_daily_queries(conn, n=22)) == 22

def test_get_daily_skips_recent(tmp_path):
    conn = init_db(path=str(tmp_path / "t.db"))
    q0 = all_queries()[0]["query"]
    conn.execute("INSERT INTO search_runs (query,district,category,results) VALUES (?,?,?,?)",
                 (q0, "Mitte", "Zahnarzt", 5))
    conn.commit()
    returned = [q["query"] for q in get_daily_queries(conn, n=110)]
    assert q0 not in returned
```

`tests/test_deduplicator.py`:
```python
from pipeline.scraper.deduplicator import url_hash, is_duplicate
from api.db import init_db

def test_hash_consistent():
    assert url_hash("https://example.com") == url_hash("https://example.com")

def test_hash_case_insensitive():
    assert url_hash("https://EXAMPLE.COM") == url_hash("https://example.com")

def test_not_duplicate_on_empty_db(tmp_path):
    conn = init_db(path=str(tmp_path / "t.db"))
    assert not is_duplicate(conn, "https://example.com")

def test_is_duplicate_after_insert(tmp_path):
    conn = init_db(path=str(tmp_path / "t.db"))
    h = url_hash("https://example.com")
    conn.execute("INSERT INTO leads (url_hash) VALUES (?)", (h,))
    conn.commit()
    assert is_duplicate(conn, "https://example.com")
```

- [ ] **Step 2: Run — expect ImportError**

```
pytest tests/test_search_queries.py tests/test_deduplicator.py -v
```

- [ ] **Step 3: Implement pipeline/scraper/search_queries.py**

```python
CATEGORIES = [
    "Zahnarzt", "Anwalt", "Immobilienmakler",
    "Physiotherapie", "Küchenstudio", "Druckerei",
    "Handwerker", "Steuerberater", "Schönheitsklinik",
    "Umzugsfirma", "Friseur",
]

DISTRICTS = [
    "Mitte", "Prenzlauer Berg", "Kreuzberg", "Charlottenburg",
    "Friedrichshain", "Neukölln", "Steglitz", "Tempelhof",
    "Pankow", "Lichtenberg",
]

def all_queries() -> list[dict]:
    return [
        {"query": f"{cat} Berlin {dist}", "category": cat, "district": dist}
        for cat in CATEGORIES
        for dist in DISTRICTS
    ]

def get_daily_queries(conn, n: int = 22) -> list[dict]:
    recent = {r["query"] for r in conn.execute(
        "SELECT query FROM search_runs WHERE ran_at > datetime('now', '-3 days')"
    ).fetchall()}
    candidates = [q for q in all_queries() if q["query"] not in recent]
    if not candidates:
        candidates = all_queries()
    return candidates[:n]
```

- [ ] **Step 4: Implement pipeline/scraper/deduplicator.py**

```python
import hashlib

def url_hash(url: str) -> str:
    return hashlib.md5(url.strip().lower().encode()).hexdigest()

def is_duplicate(conn, url: str) -> bool:
    h = url_hash(url)
    return conn.execute("SELECT 1 FROM leads WHERE url_hash=?", (h,)).fetchone() is not None
```

- [ ] **Step 5: Run — expect 9 passed**

```
pytest tests/test_search_queries.py tests/test_deduplicator.py -v
```

- [ ] **Step 6: Commit**

```
git add pipeline/scraper/search_queries.py pipeline/scraper/deduplicator.py tests/test_search_queries.py tests/test_deduplicator.py
git commit -m "feat: search query matrix with rotation and URL deduplicator"
```

---

## Task 5: Lead Scorer

**Files:** `pipeline/scorer/engine.py`, `tests/test_scorer.py`

- [ ] **Step 1: Write failing tests**

`tests/test_scorer.py`:
```python
from pipeline.scorer.engine import score_lead

def base(**kw):
    d = {"category": "Friseur", "google_reviews": 20, "red_flags": [],
         "is_mobile_ready": True, "pagespeed_mobile": 70, "seo_score": 60,
         "has_cta": True, "has_booking": True, "has_ssl": True,
         "cms_detected": None, "has_instagram": False, "has_facebook": False,
         "email": "x@y.de", "phone": "030123"}
    d.update(kw); return d

def test_high_roi_adds_3():
    assert score_lead(base(category="Zahnarzt"))["lead_score"] == \
           score_lead(base())["lead_score"] + 3

def test_no_website_adds_4():
    assert score_lead(base(red_flags=["no_website"]))["lead_score"] == \
           score_lead(base())["lead_score"] + 4

def test_many_reviews_adds_3():
    assert score_lead(base(google_reviews=60))["lead_score"] == \
           score_lead(base())["lead_score"] + 3

def test_hot_tier_at_12():
    r = score_lead(base(category="Zahnarzt", google_reviews=60,
                        red_flags=["no_website"], is_mobile_ready=False))
    assert r["lead_tier"] == "hot" and r["lead_score"] >= 12

def test_uncontactable_no_email_no_phone():
    assert score_lead(base(email=None, phone=None))["lead_tier"] == "uncontactable"

def test_fast_mobile_penalty():
    assert score_lead(base(pagespeed_mobile=85))["lead_score"] == \
           score_lead(base())["lead_score"] - 3

def test_score_never_negative():
    assert score_lead(base(pagespeed_mobile=95, cms_detected="custom",
                           google_reviews=2))["lead_score"] >= 0

def test_low_tier_default():
    assert score_lead(base())["lead_tier"] == "low"
```

- [ ] **Step 2: Run — expect ImportError**

```
pytest tests/test_scorer.py -v
```

- [ ] **Step 3: Implement pipeline/scorer/engine.py**

```python
HIGH_ROI = {"Zahnarzt", "Anwalt", "Immobilienmakler"}

def score_lead(lead: dict) -> dict:
    flags = lead.get("red_flags") or []
    score = 0

    if "no_website" in flags: score += 4
    if lead.get("category") in HIGH_ROI: score += 3
    if (lead.get("google_reviews") or 0) > 50: score += 3
    if not lead.get("is_mobile_ready") or "no_mobile" in flags: score += 3

    mobile = lead.get("pagespeed_mobile")
    if mobile is not None and mobile < 50: score += 2

    seo = lead.get("seo_score")
    if seo is not None and seo < 40: score += 2

    has_socials = lead.get("has_instagram") or lead.get("has_facebook")
    if has_socials and (not lead.get("is_mobile_ready") or "no_mobile" in flags):
        score += 2

    if not lead.get("has_cta") or "no_cta" in flags: score += 2

    cms = (lead.get("cms_detected") or "").lower()
    if any(c in cms for c in ["wix", "jimdo", "squarespace"]): score += 2
    if not lead.get("has_ssl") or "no_ssl" in flags: score += 1
    if not lead.get("has_booking") or "no_booking" in flags: score += 1

    # Penalties
    if mobile is not None and mobile > 80: score -= 3
    if cms and "custom" in cms and not any(c in cms for c in ["wix","jimdo","squarespace"]):
        score -= 2
    if (lead.get("google_reviews") or 0) < 5: score -= 1

    score = max(0, score)

    if not lead.get("email") and not lead.get("phone"):
        return {"lead_score": score, "lead_tier": "uncontactable"}

    tier = "hot" if score >= 12 else "warm" if score >= 7 else "low"
    return {"lead_score": score, "lead_tier": tier}
```

- [ ] **Step 4: Run — expect 8 passed**

```
pytest tests/test_scorer.py -v
```

- [ ] **Step 5: Commit**

```
git add pipeline/scorer/engine.py tests/test_scorer.py
git commit -m "feat: lead scoring engine with penalties and tier assignment"
```

---

## Task 6: Contact Extractor

**Files:** `pipeline/extractor/contact.py`, `tests/test_extractor.py`

- [ ] **Step 1: Write failing tests**

`tests/test_extractor.py`:
```python
from pipeline.extractor.contact import _deobfuscate, _extract_email_from_text, _extract_phone_from_text

def test_deobfuscate_bracket_at():
    assert "@" in _deobfuscate("info [at] firma.de")

def test_deobfuscate_paren_at():
    assert "@" in _deobfuscate("info(at)firma.de")

def test_deobfuscate_bracket_dot():
    assert "." in _deobfuscate("firma[dot]de")

def test_extract_plain_email():
    assert _extract_email_from_text("Kontakt: info@beispiel.de bitte") == "info@beispiel.de"

def test_extract_obfuscated_email():
    r = _extract_email_from_text("info [at] beispiel [dot] de")
    assert r == "info@beispiel.de"

def test_extract_phone_with_area():
    r = _extract_phone_from_text("Tel: 030 12345678")
    assert r is not None and "030" in r

def test_no_email_returns_none():
    assert _extract_email_from_text("Kein Kontakt hier") is None

def test_no_phone_returns_none():
    assert _extract_phone_from_text("Kein Telefon") is None
```

- [ ] **Step 2: Run — expect ImportError**

```
pytest tests/test_extractor.py -v
```

- [ ] **Step 3: Implement pipeline/extractor/contact.py**

```python
import re
import httpx

OBFUSCATION = [
    (r'\s*\[at\]\s*', '@'), (r'\s*\(at\)\s*', '@'), (r'\s+AT\s+', '@'),
    (r'\s*\[dot\]\s*', '.'), (r'\s*\(dot\)\s*', '.'),
]
EMAIL_RE = r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}'
PHONE_RE = r'(\+49[\s\-]?\d[\d\s\-]{7,}|\(0\d{2,4}\)\s?[\d\s\-]{4,}|0\d{2,4}[\s\/\-]?[\d\s\-]{4,})'
BAD_EXT = {'.png','.jpg','.gif','.svg','.css','.js','.woff','.ico'}

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
    if not matches: return None
    m = matches[0]
    return (m if isinstance(m, str) else m[0]).strip()

def extract_contacts(website: str, timeout: int = 10) -> dict:
    result = {"email": None, "phone": None}
    for path in ["/impressum", "/kontakt", "/contact", "/"]:
        try:
            resp = httpx.get(website.rstrip("/") + path, timeout=timeout,
                             follow_redirects=True,
                             headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200: continue
            text = resp.text
            if not result["email"]: result["email"] = _extract_email_from_text(text)
            if not result["phone"]: result["phone"] = _extract_phone_from_text(text)
            if result["email"] and result["phone"]: break
        except Exception:
            continue
    return result
```

- [ ] **Step 4: Run — expect 8 passed**

```
pytest tests/test_extractor.py -v
```

- [ ] **Step 5: Commit**

```
git add pipeline/extractor/contact.py tests/test_extractor.py
git commit -m "feat: contact extractor with obfuscation and phone fallback"
```

---

## Task 7: SEO + Social Analyzer

**Files:** `pipeline/analyzer/seo.py`, `pipeline/analyzer/social.py`

- [ ] **Step 1: Implement pipeline/analyzer/seo.py**

```python
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
    result = {"has_ssl": website.startswith("https://"),
              "seo_score": 0, "cms_detected": None, "red_flags": []}
    try:
        resp = httpx.get(website, timeout=timeout, follow_redirects=True, headers=HEADERS)
        soup = BeautifulSoup(resp.text, "html.parser")
        html = resp.text.lower()
        score = 0

        title = soup.find("title")
        if title and title.text.strip(): score += 20
        else: result["red_flags"].append("no_title")

        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content", "").strip(): score += 20
        else: result["red_flags"].append("no_meta")

        h1 = soup.find("h1")
        if h1 and h1.text.strip(): score += 20
        else: result["red_flags"].append("no_h1")

        for sub_path, flag in [("/robots.txt", "no_robots"), ("/sitemap.xml", "no_sitemap")]:
            try:
                r = httpx.get(website.rstrip("/") + sub_path, timeout=5, headers=HEADERS)
                if r.status_code == 200: score += 20
                else: result["red_flags"].append(flag)
            except Exception: result["red_flags"].append(flag)

        result["seo_score"] = score

        for cms, sigs in CMS_SIGS.items():
            if any(s in html for s in sigs):
                result["cms_detected"] = cms
                if cms in ("wix", "jimdo", "squarespace"):
                    result["red_flags"].append(f"{cms}_site")
                break

        if not result["has_ssl"]: result["red_flags"].append("no_ssl")

    except Exception:
        result["red_flags"].append("site_unreachable")

    return result
```

- [ ] **Step 2: Implement pipeline/analyzer/social.py**

```python
import httpx

SOCIALS = {
    "has_instagram": ["instagram.com/", "instagr.am/"],
    "has_facebook": ["facebook.com/", "fb.com/"],
    "has_linkedin": ["linkedin.com/company/", "linkedin.com/in/"],
}

def analyze_social(website: str, timeout: int = 10) -> dict:
    result = {"has_instagram": False, "has_facebook": False, "has_linkedin": False}
    try:
        resp = httpx.get(website, timeout=timeout, follow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0"})
        html = resp.text.lower()
        for key, patterns in SOCIALS.items():
            result[key] = any(p in html for p in patterns)
    except Exception:
        pass
    return result
```

- [ ] **Step 3: Commit**

```
git add pipeline/analyzer/seo.py pipeline/analyzer/social.py
git commit -m "feat: SEO analyzer with CMS detection and social link checker"
```

---

## Task 8: PageSpeed + UX Analyzer

**Files:** `pipeline/analyzer/website.py`, `pipeline/analyzer/ux.py`

- [ ] **Step 1: Implement pipeline/analyzer/website.py**

```python
import asyncio, os
import httpx

PAGESPEED_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

async def _fetch(client: httpx.AsyncClient, url: str, strategy: str) -> int | None:
    try:
        r = await client.get(PAGESPEED_URL, timeout=30,
            params={"url": url, "strategy": strategy,
                    "key": os.environ.get("GOOGLE_API_KEY", "")})
        score = (r.json().get("lighthouseResult", {})
                  .get("categories", {}).get("performance", {}).get("score"))
        return int(score * 100) if score is not None else None
    except Exception:
        return None

async def analyze_pagespeed_batch(urls: list[str], max_concurrent: int = 10) -> dict[str, dict]:
    results: dict[str, dict] = {}
    sem = asyncio.Semaphore(max_concurrent)

    async def one(url: str):
        async with sem, httpx.AsyncClient() as client:
            mobile = await _fetch(client, url, "mobile")
            desktop = await _fetch(client, url, "desktop")
        flags = []
        if mobile is not None and mobile < 50: flags.append("slow_mobile")
        if desktop is not None and desktop < 50: flags.append("slow_desktop")
        results[url] = {"pagespeed_mobile": mobile, "pagespeed_desktop": desktop,
                        "red_flags": flags}

    await asyncio.gather(*[one(u) for u in urls])
    return results
```

- [ ] **Step 2: Implement pipeline/analyzer/ux.py**

```python
import asyncio
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from playwright_stealth import stealth_async

CTA_KW = ["termin", "buchen", "kontakt", "anfrage", "reservier", "jetzt starten"]
BOOKING_KW = ["online buchen", "termin buchen", "calendly", "booking", "appointlet"]

async def _check_one(url: str, sem: asyncio.Semaphore) -> dict:
    result = {"has_cta": False, "has_booking": False,
              "is_mobile_ready": False, "red_flags": []}
    async with sem:
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                ctx = await browser.new_context(
                    viewport={"width": 375, "height": 812},
                    user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0)")
                page = await ctx.new_page()
                await stealth_async(page)
                await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                html = (await page.content()).lower()

                result["has_cta"] = any(k in html for k in CTA_KW)
                result["has_booking"] = any(k in html for k in BOOKING_KW)
                result["is_mobile_ready"] = await page.query_selector('meta[name="viewport"]') is not None

                if not result["has_cta"]: result["red_flags"].append("no_cta")
                if not result["has_booking"]: result["red_flags"].append("no_booking")
                if not result["is_mobile_ready"]: result["red_flags"].append("no_mobile")
                await browser.close()
        except PWTimeout:
            result["red_flags"].append("ux_check_timeout")
        except Exception:
            result["red_flags"].append("ux_check_timeout")
    return result

async def analyze_ux_batch(urls: list[str], max_concurrent: int = 3) -> dict[str, dict]:
    sem = asyncio.Semaphore(max_concurrent)
    results = {}
    for url in urls:
        results[url] = await _check_one(url, sem)
    return results
```

- [ ] **Step 3: Commit**

```
git add pipeline/analyzer/website.py pipeline/analyzer/ux.py
git commit -m "feat: PageSpeed async analyzer and Playwright UX checker with 30s timeout"
```

---

## Task 9: Google Maps Scraper

**Files:** `pipeline/scraper/google_maps.py`

- [ ] **Step 1: Implement pipeline/scraper/google_maps.py**

```python
import asyncio, random, re
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/123.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

async def scrape_google_maps(query: str, max_results: int = 15) -> list[dict]:
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=random.choice(UAS))
        page = await ctx.new_page()
        await stealth_async(page)

        url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(random.uniform(2, 4))

        feed = page.locator('[role="feed"]')
        for _ in range(3):
            await feed.evaluate("el => el.scrollTop += 1000")
            await asyncio.sleep(random.uniform(1, 2))

        cards = await page.query_selector_all('.Nv2PK')
        for card in cards[:max_results]:
            try:
                await card.click()
                await asyncio.sleep(random.uniform(1.5, 3))

                async def txt(sel):
                    el = await page.query_selector(sel)
                    return (await el.inner_text()).strip() if el else None

                async def attr(sel, a):
                    el = await page.query_selector(sel)
                    return await el.get_attribute(a) if el else None

                name = await txt('h1.DUwDvf')
                address = await txt('[data-item-id="address"] .Io6YTe')
                rating_el = await page.query_selector('.F7nice span[aria-hidden]')
                rating = float(await rating_el.inner_text()) if rating_el else None
                rev_el = await page.query_selector('.F7nice span[aria-label]')
                rev_text = await rev_el.get_attribute("aria-label") if rev_el else ""
                reviews = _parse_reviews(rev_text)
                website = await attr('a[data-item-id="authority"]', "href")
                phone = await txt('[data-item-id^="phone"] .Io6YTe')

                if name:
                    results.append({"name": name, "address": address,
                                    "google_rating": rating, "google_reviews": reviews,
                                    "website": website or None, "phone": phone})
            except Exception:
                continue

        await browser.close()
    return results

def _parse_reviews(text: str) -> int | None:
    m = re.search(r'(\d[\d.]*)', text.replace(',', '').replace('.', ''))
    return int(m.group(1)) if m else None
```

- [ ] **Step 2: Manual test (internet required)**

```
python -c "import asyncio; from pipeline.scraper.google_maps import scrape_google_maps; r = asyncio.run(scrape_google_maps('Zahnarzt Berlin Mitte', 3)); print(r)"
```

Expected: list of 1–3 business dicts with name, address, etc.

- [ ] **Step 3: Commit**

```
git add pipeline/scraper/google_maps.py
git commit -m "feat: Google Maps scraper with playwright-stealth and human-like delays"
```

---

## Task 10: Email Generator

**Files:** `pipeline/emailgen/generator.py`

- [ ] **Step 1: Implement pipeline/emailgen/generator.py**

```python
import json, os, re
from datetime import datetime, timedelta
from urllib.parse import urlparse
import anthropic

SYSTEM = (
    "Du bist ein professioneller Web-Berater in Berlin. "
    "Schreibe ausschließlich auf Deutsch. Maximal 150 Wörter. "
    "Keine Agentur-Buzzwords, keine Gedankenstriche. "
    "Nutze konkrete Zahlen aus den Analysedaten."
)

def _context(lead: dict) -> str:
    flags = json.loads(lead.get("red_flags") or "[]")
    return "\n".join([
        f"Firma: {lead.get('name','?')}",
        f"Branche: {lead.get('category','?')}",
        f"Bezirk: {lead.get('district','Berlin')}",
        f"Google: {lead.get('google_reviews','?')} Bewertungen, {lead.get('google_rating','?')}★",
        f"Website: {lead.get('website') or 'keine'}",
        f"Mobile PageSpeed: {lead.get('pagespeed_mobile','?')}/100",
        f"CMS: {lead.get('cms_detected','?')}",
        f"Probleme: {', '.join(flags) or 'keine'}",
    ])

def _cooldown(conn, website: str | None, days: int = 90) -> bool:
    if not website: return False
    domain = urlparse(website).netloc
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    return conn.execute("SELECT 1 FROM email_log WHERE domain=? AND sent_at>?",
                        (domain, cutoff)).fetchone() is not None

def _parse(raw: str) -> tuple[str, str]:
    lines = raw.strip().splitlines()
    subject, body_lines = "", []
    for line in lines:
        if line.lower().startswith("betreff:"):
            subject = line.split(":", 1)[1].strip()
        elif subject:
            body_lines.append(line)
    body = "\n".join(body_lines).strip()
    if not subject:
        subject = "Ihre Online-Präsenz in Berlin"
        body = raw.strip()
    return subject, body

def generate_emails(lead: dict, conn, dry_run: bool = False) -> dict | None:
    if not lead.get("email"): return None
    if _cooldown(conn, lead.get("website")): return None

    if dry_run:
        return {"subject": f"[DRY RUN] {lead.get('name','?')}",
                "body_a": "[DRY RUN] Variante A", "body_b": "[DRY RUN] Variante B"}

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    ctx = _context(lead)

    def call(instruction: str) -> str:
        return client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=500,
            system=SYSTEM,
            messages=[{"role": "user", "content":
                f"Outreach-Email:\n\n{ctx}\n\nAnsatz: {instruction}\n\n"
                f"Format:\nBetreff: [Betreff]\n\n[Email-Text]"}]
        ).content[0].text

    subj, body_a = _parse(call("Konkrete Probleme und deren Auswirkung auf Kunden nennen."))
    _, body_b = _parse(call("Verpasstes Potenzial und Wachstumschance betonen."))

    return {"subject": subj, "body_a": body_a, "body_b": body_b}
```

- [ ] **Step 2: Commit**

```
git add pipeline/emailgen/generator.py
git commit -m "feat: Claude Haiku email generator, 2 DE variants, 90-day cooldown"
```

---

## Task 11: Orchestrator

**Files:** `pipeline/run.py`

- [ ] **Step 1: Implement pipeline/run.py**

```python
import argparse, asyncio, json, logging, sys
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

from api.db import init_db, get_conn
from pipeline.scraper.search_queries import get_daily_queries
from pipeline.scraper.deduplicator import url_hash, is_duplicate
from pipeline.scraper.google_maps import scrape_google_maps
from pipeline.analyzer.seo import analyze_seo
from pipeline.analyzer.social import analyze_social
from pipeline.analyzer.website import analyze_pagespeed_batch
from pipeline.analyzer.ux import analyze_ux_batch
from pipeline.extractor.contact import extract_contacts
from pipeline.scorer.engine import score_lead
from pipeline.emailgen.generator import generate_emails

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler("pipeline.log"), logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)

def run(dry_run: bool = False):
    conn = init_db()
    c = {"new": 0, "hot": 0, "warm": 0, "low": 0, "uncontactable": 0, "skipped": 0}

    # Stage 1: Scrape
    queries = get_daily_queries(conn, n=22)
    log.info(f"Stage 1: {len(queries)} queries")
    raw: list[dict] = []

    for q in tqdm(queries, desc="Scraping"):
        try:
            results = asyncio.run(scrape_google_maps(q["query"], max_results=15))
            for r in results:
                r["category"] = q["category"]; r["district"] = q["district"]
            raw.extend(results)
            if not dry_run:
                conn.execute("INSERT INTO search_runs (query,district,category,results) VALUES (?,?,?,?)",
                             (q["query"], q["district"], q["category"], len(results)))
                conn.commit()
        except Exception as e:
            log.error(f"Scrape error {q['query']}: {e}")

    # Deduplicate + insert
    for lead in raw:
        site = lead.get("website") or ""
        key = site if site else f"nw-{lead.get('name','')}-{lead.get('address','')}"
        if is_duplicate(conn, key):
            c["skipped"] += 1; continue
        c["new"] += 1
        if not dry_run:
            h = url_hash(key)
            conn.execute(
                "INSERT INTO leads (url_hash,name,category,district,address,phone,website,google_rating,google_reviews)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (h, lead.get("name"), lead.get("category"), lead.get("district"),
                 lead.get("address"), lead.get("phone"), site or None,
                 lead.get("google_rating"), lead.get("google_reviews")))
            conn.commit()

    log.info(f"New: {c['new']} | Skipped: {c['skipped']}")
    if dry_run:
        log.info("DRY RUN done."); return

    # Stage 2: Analyze
    pending = [dict(r) for r in conn.execute("SELECT * FROM leads WHERE stage='scraped'").fetchall()]
    with_site = [r for r in pending if r.get("website")]
    no_site = [r for r in pending if not r.get("website")]

    for lead in no_site:
        conn.execute("UPDATE leads SET stage='analyzed', red_flags=? WHERE id=?",
                     (json.dumps(["no_website"]), lead["id"]))
    conn.commit()

    if with_site:
        log.info(f"Stage 2: {len(with_site)} websites")
        urls = [r["website"] for r in with_site]
        ps_results = asyncio.run(analyze_pagespeed_batch(urls))
        ux_results = asyncio.run(analyze_ux_batch(urls))

        for lead in tqdm(with_site, desc="Analyzing"):
            url = lead["website"]
            ps = ps_results.get(url, {})
            ux = ux_results.get(url, {})
            seo = analyze_seo(url)
            social = analyze_social(url)
            flags = list(set(ps.get("red_flags",[]) + ux.get("red_flags",[]) + seo.get("red_flags",[])))
            conn.execute(
                "UPDATE leads SET pagespeed_mobile=?,pagespeed_desktop=?,has_ssl=?,cms_detected=?,"
                "has_cta=?,has_booking=?,is_mobile_ready=?,seo_score=?,has_instagram=?,has_facebook=?,"
                "has_linkedin=?,red_flags=?,stage='analyzed',updated_at=datetime('now') WHERE id=?",
                (ps.get("pagespeed_mobile"), ps.get("pagespeed_desktop"),
                 1 if seo.get("has_ssl") else 0, seo.get("cms_detected"),
                 1 if ux.get("has_cta") else 0, 1 if ux.get("has_booking") else 0,
                 1 if ux.get("is_mobile_ready") else 0, seo.get("seo_score"),
                 1 if social.get("has_instagram") else 0, 1 if social.get("has_facebook") else 0,
                 1 if social.get("has_linkedin") else 0, json.dumps(flags), lead["id"]))
        conn.commit()

    # Stage 3: Extract contacts
    to_extract = [dict(r) for r in conn.execute("SELECT * FROM leads WHERE stage='analyzed'").fetchall()]
    for lead in tqdm(to_extract, desc="Extracting"):
        contacts = extract_contacts(lead["website"]) if lead.get("website") else {"email": None, "phone": None}
        phone = contacts.get("phone") or lead.get("phone")
        conn.execute("UPDATE leads SET email=?,phone=?,stage='extracted',updated_at=datetime('now') WHERE id=?",
                     (contacts.get("email"), phone, lead["id"]))
    conn.commit()

    # Stage 4: Score
    to_score = [dict(r) for r in conn.execute("SELECT * FROM leads WHERE stage='extracted'").fetchall()]
    for lead in tqdm(to_score, desc="Scoring"):
        lead["red_flags"] = json.loads(lead.get("red_flags") or "[]")
        r = score_lead(lead)
        conn.execute("UPDATE leads SET lead_score=?,lead_tier=?,stage='scored',updated_at=datetime('now') WHERE id=?",
                     (r["lead_score"], r["lead_tier"], lead["id"]))
        c[r["lead_tier"]] = c.get(r["lead_tier"], 0) + 1
    conn.commit()

    # Stage 5: Generate emails
    to_email = [dict(r) for r in conn.execute(
        "SELECT * FROM leads WHERE stage='scored' AND lead_tier IN ('hot','warm')"
    ).fetchall()]
    for lead in tqdm(to_email, desc="Generating emails"):
        emails = generate_emails(lead, conn)
        if emails:
            conn.execute(
                "UPDATE leads SET email_subject=?,email_body_a=?,email_body_b=?,"
                "stage='email_ready',updated_at=datetime('now') WHERE id=?",
                (emails["subject"], emails["body_a"], emails["body_b"], lead["id"]))
        else:
            conn.execute("UPDATE leads SET stage='email_ready',updated_at=datetime('now') WHERE id=?",
                         (lead["id"],))
    conn.commit()

    log.info(f"Done | New:{c['new']} Hot:{c['hot']} Warm:{c['warm']} "
             f"Low:{c['low']} Uncontactable:{c['uncontactable']} Skipped:{c['skipped']}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    run(dry_run=parser.parse_args().dry_run)
```

- [ ] **Step 2: Test dry run**

```
python pipeline\run.py --dry-run
```

Expected: stages log, no DB writes, no Claude API calls, summary printed.

- [ ] **Step 3: Commit**

```
git add pipeline/run.py
git commit -m "feat: pipeline orchestrator with tqdm, logging, stage tracking, --dry-run"
```

---

## Task 12: Next.js Dashboard

**Files:** `dashboard/` app, `src/lib/api.ts`, `src/app/page.tsx`, `src/app/leads/[id]/page.tsx`, `src/app/leads/[id]/EmailPanel.tsx`

- [ ] **Step 1: Init Next.js**

```
npx create-next-app@14 dashboard --typescript --tailwind --app --no-src-dir --import-alias "@/*" --yes
```

- [ ] **Step 2: Create dashboard/app/lib/api.ts**

```typescript
const API = "http://localhost:8000";

export interface LeadSummary {
  id: number; name: string | null; category: string | null; district: string | null;
  lead_score: number | null; lead_tier: string | null; stage: string; status: string;
  has_email: boolean; follow_up_due: boolean; created_at: string;
}
export interface LeadDetail {
  id: number; name: string | null; category: string | null; district: string | null;
  address: string | null; phone: string | null; email: string | null; website: string | null;
  google_rating: number | null; google_reviews: number | null;
  has_instagram: boolean; has_facebook: boolean; has_linkedin: boolean;
  pagespeed_mobile: number | null; pagespeed_desktop: number | null;
  has_ssl: boolean | null; cms_detected: string | null;
  has_cta: boolean | null; has_booking: boolean | null; is_mobile_ready: boolean | null;
  seo_score: number | null; red_flags: string[];
  lead_score: number | null; lead_tier: string | null; stage: string;
  email_subject: string | null; email_body_a: string | null; email_body_b: string | null;
  email_approved: boolean; email_variant: string | null;
  status: string; notes: string | null; created_at: string; updated_at: string;
}
export interface Stats {
  hot: number; warm: number; low: number; new_today: number; contacted: number; replied: number;
}

export const getStats = (): Promise<Stats> =>
  fetch(`${API}/stats`, { cache: "no-store" }).then(r => r.json());

export const getLeads = (p?: Record<string, string>): Promise<LeadSummary[]> =>
  fetch(`${API}/leads${p ? "?" + new URLSearchParams(p) : ""}`, { cache: "no-store" }).then(r => r.json());

export const getLead = (id: number): Promise<LeadDetail> =>
  fetch(`${API}/leads/${id}`, { cache: "no-store" }).then(r => r.json());

export const approveEmail = (id: number, variant: "a" | "b") =>
  fetch(`${API}/leads/${id}/approve-email`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ variant }),
  });

export const updateStatus = (id: number, status: string) =>
  fetch(`${API}/leads/${id}/status`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
```

- [ ] **Step 3: Create dashboard/app/page.tsx**

```tsx
import { getStats, getLeads } from "@/lib/api";

const TIER: Record<string, string> = {
  hot: "bg-red-100 text-red-700", warm: "bg-orange-100 text-orange-700", low: "bg-gray-100 text-gray-500",
};

export default async function Home({ searchParams }: { searchParams: Record<string, string> }) {
  const [stats, leads] = await Promise.all([getStats(), getLeads(searchParams)]);
  return (
    <div className="min-h-screen bg-gray-50">
      <div className="flex gap-6 p-4 bg-white border-b text-sm font-medium">
        <span>Heute: <b>{stats.new_today}</b></span>
        <span className="text-red-600">Hot: <b>{stats.hot}</b></span>
        <span className="text-orange-500">Warm: <b>{stats.warm}</b></span>
        <span className="text-gray-400">Low: <b>{stats.low}</b></span>
        <span>Contacted: <b>{stats.contacted}</b></span>
        <span className="text-green-600">Replied: <b>{stats.replied}</b></span>
      </div>
      <div className="flex gap-2 p-3 bg-white border-b text-sm">
        {["hot","warm","low"].map(t => (
          <a key={t} href={`?tier=${t}`} className="px-3 py-1 border rounded hover:bg-gray-50 capitalize">{t}</a>
        ))}
        <a href="/" className="px-3 py-1 border rounded hover:bg-gray-50">Alle</a>
      </div>
      <table className="w-full text-sm bg-white">
        <thead className="border-b text-xs text-gray-500 uppercase">
          <tr>{["Firma","Branche","Bezirk","Score","Tier","Stage","Email","Status",""].map(h =>
            <th key={h} className="px-4 py-3 text-left">{h}</th>)}</tr>
        </thead>
        <tbody>
          {leads.map(l => (
            <tr key={l.id} className="border-b hover:bg-gray-50">
              <td className="px-4 py-3 font-medium">{l.name ?? "—"}</td>
              <td className="px-4 py-3 text-gray-500">{l.category}</td>
              <td className="px-4 py-3 text-gray-500">{l.district}</td>
              <td className="px-4 py-3">{l.lead_score ?? "—"}</td>
              <td className="px-4 py-3">
                {l.lead_tier && <span className={`px-2 py-0.5 rounded text-xs font-semibold ${TIER[l.lead_tier]}`}>{l.lead_tier.toUpperCase()}</span>}
              </td>
              <td className="px-4 py-3 text-gray-400 text-xs">{l.stage}</td>
              <td className="px-4 py-3">{l.has_email ? "✓" : "—"}</td>
              <td className="px-4 py-3">
                {l.follow_up_due
                  ? <span className="text-orange-500 font-semibold text-xs">Follow-up fällig</span>
                  : l.status}
              </td>
              <td className="px-4 py-3">
                <a href={`/leads/${l.id}`} className="text-blue-600 hover:underline">Detail →</a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 4: Create dashboard/app/leads/[id]/page.tsx**

```tsx
import { getLead } from "@/lib/api";
import EmailPanel from "./EmailPanel";

function Bar({ label, v }: { label: string; v: number | null }) {
  if (v === null) return <div className="text-gray-400 text-xs mb-2">{label}: —</div>;
  const col = v >= 70 ? "bg-green-500" : v >= 50 ? "bg-yellow-400" : "bg-red-500";
  return (
    <div className="mb-3">
      <div className="flex justify-between text-xs mb-1"><span>{label}</span><span>{v}/100</span></div>
      <div className="h-1.5 bg-gray-200 rounded"><div className={`h-1.5 rounded ${col}`} style={{ width: `${v}%` }} /></div>
    </div>
  );
}

export default async function LeadPage({ params }: { params: { id: string } }) {
  const lead = await getLead(Number(params.id));
  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <a href="/" className="text-blue-600 text-sm hover:underline mb-4 block">← Zurück</a>
      <div className="grid grid-cols-2 gap-6">
        <div className="space-y-4">
          <div className="bg-white rounded-lg p-5 border">
            <h1 className="text-xl font-bold">{lead.name}</h1>
            <p className="text-gray-500 text-sm">{lead.category} · {lead.district}</p>
            {lead.website && <a href={lead.website} target="_blank" className="text-blue-600 text-sm block mt-1">{lead.website}</a>}
            {lead.phone && <p className="text-sm mt-1">📞 {lead.phone}</p>}
            {lead.email && <p className="text-sm mt-1">✉️ {lead.email}</p>}
            <p className="text-sm text-gray-500 mt-2">⭐ {lead.google_rating ?? "—"} · {lead.google_reviews ?? 0} Bewertungen</p>
          </div>
          <div className="bg-white rounded-lg p-5 border">
            <h2 className="font-semibold text-sm mb-3">Analyse</h2>
            <Bar label="Mobile Speed" v={lead.pagespeed_mobile} />
            <Bar label="Desktop Speed" v={lead.pagespeed_desktop} />
            <Bar label="SEO Score" v={lead.seo_score} />
            <div className="flex flex-wrap gap-1 mt-3">
              {lead.red_flags.map(f => (
                <span key={f} className="px-2 py-0.5 bg-red-50 text-red-600 text-xs rounded">{f}</span>
              ))}
            </div>
          </div>
        </div>
        <EmailPanel lead={lead} />
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Create dashboard/app/leads/[id]/EmailPanel.tsx**

```tsx
"use client";
import { useState } from "react";
import { LeadDetail, approveEmail, updateStatus } from "@/lib/api";

export default function EmailPanel({ lead }: { lead: LeadDetail }) {
  const [approved, setApproved] = useState(lead.email_approved);
  const [status, setStatus] = useState(lead.status);

  if (!lead.email_body_a && !lead.email_body_b) {
    return (
      <div className="bg-white rounded-lg p-5 border text-gray-400 text-sm">
        {lead.stage !== "email_ready" ? `Stage: ${lead.stage}` : "Kein Email-Kontakt gefunden"}
      </div>
    );
  }

  const mailto = (body: string) => {
    const s = encodeURIComponent(lead.email_subject || "Ihre Online-Präsenz in Berlin");
    const b = encodeURIComponent(body);
    return `mailto:${lead.email ?? ""}?subject=${s}&body=${b}`;
  };

  const handleSend = async (v: "a" | "b") => {
    await approveEmail(lead.id, v);
    setApproved(true); setStatus("contacted");
  };

  return (
    <div className="space-y-4">
      {approved && (
        <div className="bg-green-50 border border-green-200 rounded p-3 text-green-700 text-sm">
          ✓ Freigegeben (Variante {lead.email_variant?.toUpperCase()})
        </div>
      )}
      {(["a","b"] as const).map(v => {
        const body = v === "a" ? lead.email_body_a : lead.email_body_b;
        if (!body) return null;
        return (
          <div key={v} className="bg-white rounded-lg p-5 border">
            <h3 className="font-semibold text-sm mb-2">
              {v === "a" ? "Variante A — Problem-fokussiert" : "Variante B — Opportunity-fokussiert"}
            </h3>
            <pre className="text-xs text-gray-700 whitespace-pre-wrap mb-4 font-sans leading-relaxed">{body}</pre>
            {!approved ? (
              <a href={mailto(body)} onClick={() => handleSend(v)}
                 className="inline-block px-4 py-2 bg-blue-600 text-white text-sm rounded hover:bg-blue-700">
                Diese senden →
              </a>
            ) : (
              <span className="text-gray-400 text-sm">Bereits freigegeben</span>
            )}
          </div>
        );
      })}
      <div className="bg-white rounded-lg p-5 border">
        <h3 className="font-semibold text-sm mb-2">CRM Status</h3>
        <div className="flex gap-2 flex-wrap">
          {["new","contacted","replied","closed","ignored"].map(s => (
            <button key={s} onClick={async () => { await updateStatus(lead.id, s); setStatus(s); }}
                    className={`px-3 py-1 text-xs rounded border ${status===s ? "bg-gray-800 text-white" : "hover:bg-gray-50"}`}>
              {s}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Start dashboard and verify**

```
cd dashboard && npm run dev
```

Open `http://localhost:3000` — lead table loads (empty until pipeline runs).
Open `http://localhost:3000/leads/1` after seeding a lead — detail page renders.

- [ ] **Step 7: Commit**

```
git add dashboard/
git commit -m "feat: Next.js dashboard with lead table, detail page, email panel, and mailto flow"
```

---

## Task 13: Windows Scripts + Full Test Run

**Files:** `scripts/*.bat`

- [ ] **Step 1: Create scripts**

`scripts/run_pipeline.bat`:
```bat
@echo off
cd /d %~dp0..
python pipeline\run.py
pause
```

`scripts/run_dry.bat`:
```bat
@echo off
cd /d %~dp0..
python pipeline\run.py --dry-run
pause
```

`scripts/start_api.bat`:
```bat
@echo off
cd /d %~dp0..
uvicorn api.main:app --reload --port 8000
```

`scripts/start_dashboard.bat`:
```bat
@echo off
cd /d %~dp0..
cd dashboard && npm run dev
```

- [ ] **Step 2: Run full test suite**

```
pytest tests/ -v
```

Expected: all tests pass (test_db, test_models, test_search_queries, test_deduplicator, test_scorer, test_extractor).

- [ ] **Step 3: Full dry-run**

```
scripts\run_dry.bat
```

Expected: all 5 stages log, summary printed, `pipeline.log` created, no DB or API writes.

- [ ] **Step 4: Commit**

```
git add scripts/
git commit -m "chore: Windows .bat scripts and verified full dry-run"
```

---

## Self-Review

**Spec coverage:**

| Requirement | Task |
|---|---|
| Google Maps scraping + stealth | 9 |
| Query rotation via search_runs | 4 |
| URL deduplication | 4 |
| No-website fast-track | 11 |
| PageSpeed async + concurrent | 8 |
| SEO + CMS detection | 7 |
| Social detection | 7 |
| UX check, 30s timeout | 8 |
| Contact extraction + obfuscation | 6 |
| Phone fallback | 6 |
| Scoring + penalties | 5 |
| Uncontactable filter | 5 |
| Claude Haiku, 2 DE variants | 10 |
| 90-day cooldown | 10 |
| --dry-run | 11 |
| tqdm + logging | 11 |
| Stage tracking | 11 |
| All 6 FastAPI endpoints | 3 |
| CORS | 3 |
| WAL mode | 2 |
| Stats bar | 12 |
| Filter bar | 12 |
| Follow-up badge | 12 |
| Email variants + mailto | 12 |
| CRM status buttons | 12 |
| Windows scripts | 13 |

All requirements covered. No placeholders. Function names consistent across tasks (`score_lead`, `generate_emails`, `extract_contacts`, `url_hash`, `is_duplicate`, `get_daily_queries`, `scrape_google_maps`, `analyze_seo`, `analyze_social`, `analyze_pagespeed_batch`, `analyze_ux_batch`).
