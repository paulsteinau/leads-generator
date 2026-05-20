# Berlin Lead-Gen System — Design Spec
**Date:** 2026-05-19
**Status:** Approved

---

## Kontext

Internes, lokales Tool zur automatisierten Identifikation und Kontaktaufnahme mit Berliner Businesses die erkennbare Schwächen in ihrer Online-Präsenz haben. Ziel: 50 hochqualifizierte Leads/Tag, kein generisches Cold Outreach.

---

## Entscheidungen (aus Brainstorming)

| Frage | Entscheidung |
|---|---|
| Budget für paid APIs | Nein — kosteneffizient, kein SerpAPI/Apify |
| Ziel-Volumen | 50 qualifizierte Leads/Tag |
| Wo läuft es | Lokal (Windows 11) |
| Email-Versand | Manuell freigeben, nie automatisch senden |
| Sprache | Python (Backend) + Next.js (Dashboard) |
| LLM | Claude Haiku via Anthropic API |
| Datenbank | SQLite lokal (WAL-Mode) |
| Email-Send-Mechanismus | `mailto:` Link öffnet Standard-Mailprogramm |

---

## Tech Stack

```
Backend Pipeline:  Python 3.12
Scraping:          Playwright + playwright-stealth
HTTP:              httpx (10s timeout, 1 retry)
Concurrency:       asyncio (PageSpeed), ThreadPoolExecutor (Playwright)
LLM:               Anthropic Claude Haiku
API Layer:         FastAPI (sync sqlite3, kein ORM)
Dashboard:         Next.js 14 + Tailwind CSS
Datenbank:         SQLite (WAL-Mode, eine Datei: data/leads.db)
Progress:          tqdm
Logging:           Python logging → pipeline.log
```

---

## Systemarchitektur

```
[scripts/run_pipeline.py]        [scripts/start_api.py]   [dashboard/]
       ↓                                ↓                       ↓
[pipeline/scraper]               [api/main.py]           [Next.js App]
[pipeline/analyzer]    →→→      [api/db.py]      ←←←    [localhost:3000]
[pipeline/extractor]            [FastAPI]
[pipeline/scorer]                    ↕
[pipeline/emailgen]             [data/leads.db]
                                  (SQLite WAL)
```

Flow pro Lead:
`scraped → analyzed → extracted → scored → email_ready → approved → sent`

---

## Folder Structure

```
berlin-leads/
├── pipeline/
│   ├── scraper/
│   │   ├── google_maps.py        # Playwright+Stealth → Google Maps
│   │   ├── search_queries.py     # Bezirk × Branche Query-Matrix + Rotation
│   │   └── deduplicator.py       # URL-Hash Duplikat-Check via DB
│   ├── analyzer/
│   │   ├── website.py            # PageSpeed API (async/concurrent, max 10)
│   │   ├── seo.py                # Meta, Title, H1, robots.txt via httpx
│   │   ├── ux.py                 # CTA, Mobile, SSL via Playwright (30s timeout)
│   │   └── social.py             # Instagram/Facebook/LinkedIn Link-Check
│   ├── extractor/
│   │   └── contact.py            # Impressum→Contact→Homepage→Maps, obfusk. Emails, tel: Fallback
│   ├── scorer/
│   │   └── engine.py             # Gewichtetes Scoring + Penalties + Uncontactable-Filter
│   ├── emailgen/
│   │   └── generator.py          # Claude Haiku, 2 Varianten (DE), 90-Tage Cooldown
│   └── run.py                    # Orchestrator: alle Stages, Logging, tqdm, --dry-run
├── api/
│   ├── main.py                   # FastAPI + CORS (localhost:3000)
│   ├── models.py                 # Pydantic Schemas
│   └── db.py                     # SQLite + WAL-Mode Init + Schema
├── dashboard/
│   └── src/app/
│       ├── page.tsx              # Lead-Tabelle + Stats-Bar + Filter
│       └── leads/[id]/page.tsx   # Lead-Detail + Email-Varianten + Approve
├── data/
│   └── leads.db                  # SQLite Datenbank (gitignored)
├── scripts/
│   ├── run_pipeline.bat          # Windows: python pipeline/run.py
│   ├── start_api.bat             # Windows: uvicorn api.main:app
│   └── start_dashboard.bat       # Windows: npm run dev
├── .env                          # ANTHROPIC_API_KEY, GOOGLE_API_KEY
├── requirements.txt
└── README.md
```

---

## Datenbankschema

```sql
PRAGMA journal_mode=WAL;  -- beim DB-Init gesetzt (Fix: concurrent access)

CREATE TABLE leads (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    url_hash          TEXT UNIQUE NOT NULL,    -- Idempotenz-Key (MD5 der Website-URL)
    name              TEXT,
    category          TEXT,
    district          TEXT,
    address           TEXT,
    phone             TEXT,
    email             TEXT,
    website           TEXT,                   -- NULL = keine Website
    google_rating     REAL,
    google_reviews    INTEGER,
    has_instagram     BOOLEAN,
    has_facebook      BOOLEAN,
    has_linkedin      BOOLEAN,

    -- Analyse
    pagespeed_mobile  INTEGER,                -- 0–100
    pagespeed_desktop INTEGER,
    has_ssl           BOOLEAN,
    cms_detected      TEXT,                   -- "WordPress","Wix","Custom",NULL
    has_cta           BOOLEAN,
    has_booking       BOOLEAN,
    is_mobile_ready   BOOLEAN,
    seo_score         INTEGER,                -- 0–100
    red_flags         TEXT,                   -- JSON Array

    -- Scoring
    lead_score        INTEGER,
    lead_tier         TEXT,                   -- "hot","warm","low","uncontactable"

    -- Stage-Tracking
    stage             TEXT DEFAULT 'scraped', -- scraped→analyzed→extracted→scored→email_ready→approved→sent

    -- Email
    email_subject     TEXT,
    email_body_a      TEXT,                   -- Variante A: Problem-fokussiert
    email_body_b      TEXT,                   -- Variante B: Opportunity-fokussiert
    email_approved    BOOLEAN DEFAULT FALSE,
    email_variant     TEXT,                   -- "a" oder "b"
    email_sent_at     DATETIME,

    -- CRM
    status            TEXT DEFAULT 'new',     -- new→contacted→replied→closed→ignored
    notes             TEXT,
    created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE search_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    query       TEXT,
    district    TEXT,
    category    TEXT,
    results     INTEGER,
    ran_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE email_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id     INTEGER REFERENCES leads(id),
    domain      TEXT,                         -- für 90-Tage Cooldown-Check
    sent_at     DATETIME,
    subject     TEXT,
    body        TEXT,
    reply       TEXT,
    replied_at  DATETIME
);
```

---

## Pipeline Stages (Detail)

### Stage 1 — Scraper

**Inputs:** Query-Matrix (Branche × Bezirk)
**Output:** DB records mit `stage='scraped'`

Query-Matrix:
- Branchen: Zahnarzt, Anwalt, Physiotherapie, Immobilienmakler, Friseur, Küchenstudio, Druckerei, Handwerker, Steuerberater, Schönheitsklinik, Umzugsfirma
- Bezirke: Mitte, Prenzlauer Berg, Kreuzberg, Charlottenburg, Friedrichshain, Neukölln, Steglitz, Tempelhof, Pankow, Lichtenberg
- ~110 Kombinationen total

Täglich 20–25 Queries aus Rotation (via `search_runs` Tabelle — wählt älteste).
Max 15 Businesses pro Query → max ~375 raw, ~50 qualifiziert nach Scoring.

Stealth-Setup:
- `playwright-stealth` (Bot-Fingerprint Patches)
- Random Delays: 2–6s zwischen Requests
- `channel='chromium'` headless, kein sichtbares Fenster
- User-Agent Rotation

Deduplication: MD5-Hash der Website-URL. Existiert bereits in DB → skip.
Businesses ohne Website: `website=NULL` → trotzdem speichern, höchster Score.

---

### Stage 2 — Analyzer

**Input:** Leads mit `stage='scraped'` UND `website IS NOT NULL`
**Output:** Analyse-Felder befüllt, `stage='analyzed'`

Leads ohne Website: direkt `stage='analyzed'`, `red_flags='["no_website"]'`

Sub-Module:

**website.py** (async/concurrent, max 10 gleichzeitig):
- Google PageSpeed Insights API (kostenloser API-Key erforderlich)
- Liefert: pagespeed_mobile, pagespeed_desktop

**seo.py** (httpx, 10s timeout, 1 retry):
- Prüft: Title-Tag, Meta-Description, H1, robots.txt, sitemap.xml

**ux.py** (Playwright + Stealth, 30s Timeout pro Session):
- Prüft: CTA-Buttons (Text: Termin/Buchen/Kontakt/Anfrage), SSL-Redirect, Viewport/Mobile
- Bei Timeout: Session killen, `red_flags` += `"ux_check_timeout"`, weiter

**social.py** (httpx):
- Sucht Links zu instagram.com, facebook.com, linkedin.com auf der Homepage

Red Flags JSON Array — mögliche Werte:
`no_website, no_ssl, slow_mobile, slow_desktop, no_cta, no_booking,
 no_mobile, wix_site, jimdo_site, squarespace_site, wordpress_outdated,
 no_meta, no_h1, no_sitemap, no_socials, site_unreachable, ux_check_timeout`

---

### Stage 3 — Contact Extractor

**Input:** Leads mit `stage='analyzed'`
**Output:** `email` und/oder `phone` befüllt, `stage='extracted'`

Prioritätsreihenfolge Email-Suche:
1. `/impressum` scrapen → Regex nach Email
2. `/kontakt` oder `/contact` scrapen
3. Homepage scrapen (mailto: Links)
4. Google Maps Eintrag
5. Kein Email → `email=NULL`

Obfuskierung auflösen: `[at]`, `(at)`, ` AT `, `[dot]` → echte Email-Adresse.

Telefon-Fallback: `tel:` Links auf allen gescrapten Seiten — befüllt `phone` falls noch nicht vorhanden.

Leads ohne Email UND ohne Telefon → `lead_tier='uncontactable'` im Scorer.

---

### Stage 4 — Scorer

**Input:** Leads mit `stage='extracted'`
**Output:** `lead_score`, `lead_tier`, `stage='scored'`

Positive Signale:

| Signal | Punkte |
|---|---|
| Keine Website | +4 |
| High-ROI Branche (Zahnarzt, Anwalt, Immobilien) | +3 |
| Viele Reviews (>50) | +3 |
| Keine Mobile-Optimierung | +3 |
| Schlechte Ladezeit (Mobile PageSpeed <50) | +2 |
| Keine SEO-Basis (kein Title/Meta/H1) | +2 |
| Aktive Socials aber schwache Website | +2 |
| Kein CTA | +2 |
| Wix/Jimdo/Squarespace erkannt | +2 |
| Kein SSL | +1 |
| Kein Buchungssystem | +1 |

Negative Signale (Penalties):

| Signal | Punkte |
|---|---|
| PageSpeed Mobile >80 | -3 |
| Modernes Custom-CMS erkannt | -2 |
| Sehr wenig Reviews (<5) | -1 |

Tiers:
- **hot** → Score ≥ 12
- **warm** → Score 7–11
- **low** → Score < 7
- **uncontactable** → kein Email + kein Telefon (Score irrelevant)

---

### Stage 5 — Email Generator

**Input:** Leads mit `stage='scored'` UND `lead_tier IN ('hot','warm')`
**Output:** `email_subject`, `email_body_a`, `email_body_b`, `stage='email_ready'`

Checks vor Generierung:
- 90-Tage Cooldown: prüfe `email_log` ob `domain` in letzten 90 Tagen kontaktiert → skip
- `email IS NULL` → skip (kein Kontakt möglich)

Claude Haiku Prompt-Struktur:
- System: "Schreibe ausschließlich auf Deutsch. Max 150 Wörter. Keine Agentur-Sprache. Keine em-Dashes. Konkrete Zahlen aus der Analyse verwenden."
- User: Lead-Daten + Red Flags + Score-Begründung
- Output: 2 Varianten
  - **Variante A** (Problem-fokussiert): Nennt konkrete Schwächen direkt
  - **Variante B** (Opportunity-fokussiert): Fokus auf entgangenes Potenzial

Dynamische Bausteine je nach Red Flags:
- `slow_mobile` → "Ihre Website lädt auf Mobilgeräten in [X]s"
- `no_cta` → "kein klarer nächster Schritt für Besucher sichtbar"
- `wix_site` → "aktuelles Setup limitiert Wachstum und Anpassbarkeit"
- viele Reviews + schwache Website → "[X] Bewertungen zeigen aktive Kundenbasis — die Website konvertiert das nicht"

---

### Orchestrator (run.py)

```
python pipeline/run.py            # normaler Run
python pipeline/run.py --dry-run  # kein DB-Write, kein Claude-API-Call
```

Ablauf:
1. Logging init → `pipeline.log`
2. Stage 1: Scraper (20–25 Queries aus Rotation, tqdm)
3. Stage 2: Analyzer (async PageSpeed + Playwright-Pool, tqdm)
4. Stage 2b: No-Website Leads → direkt weiter
5. Stage 3: Extractor (tqdm)
6. Stage 4: Scorer (tqdm)
7. Stage 5: Email Gen (nur Hot+Warm, Cooldown-Check, tqdm)
8. Log-Summary: X neue Leads | Y Hot | Z Warm | N uncontactable | M übersprungen

Laufzeit: ~15–20 Minuten für 50 Leads.

---

## FastAPI Endpoints

```
GET  /leads                        → Leadliste (Filter: tier, stage, district, category)
GET  /leads/{id}                   → Lead-Detail inkl. beide Email-Varianten
POST /leads/{id}/approve-email     → Body: {"variant": "a"|"b"} → email_approved=true
POST /leads/{id}/status            → Body: {"status": "contacted"|"replied"|"closed"|"ignored"}
GET  /stats                        → {hot, warm, low, new_today, contacted, replied}
GET  /leads/export                 → CSV aller Leads (Query-Param: tier)
```

CORS: `allow_origins=["http://localhost:3000"]`
SQLite WAL-Mode wird bei `db.py` Import gesetzt.

---

## Next.js Dashboard

### Seite 1 — `/` (Hauptseite)

**Stats-Bar oben:** Heute neu: X | Hot: Y | Warm: Z | Contacted: N | Replied: M

**Filter-Bar:** Tier (Hot/Warm/Low), Bezirk, Branche, Stage

**Lead-Tabelle:** Name | Branche | Bezirk | Score-Badge | Stage | Email? | Status | Follow-up?

Follow-up Badge: Wenn `status='contacted'` und `updated_at` > 7 Tage → oranger Badge "Follow-up fällig"

**Uncontactable-Sektion:** Ausklappbar am Ende der Seite, separater Bereich.

### Seite 2 — `/leads/[id]` (Detail)

**Linke Spalte:** Firmeninfos, Red Flags als Tags, PageSpeed-Score visuell (Farbbalken), Social-Badges, Notes-Feld

**Rechte Spalte:** 
- Email Variante A + Variante B nebeneinander
- "Diese senden" Button unter jeder Variante → öffnet `mailto:email@firma.de?subject=...&body=...`
- Nach Approve: Email gesperrt, Status springt auf `contacted`

---

## Windows Scripts (statt Makefile)

```
scripts/run_pipeline.bat    → python pipeline\run.py
scripts/run_dry.bat         → python pipeline\run.py --dry-run
scripts/start_api.bat       → uvicorn api.main:app --reload --port 8000
scripts/start_dashboard.bat → cd dashboard && npm run dev
```

Täglicher Run: Windows Task Scheduler → `scripts/run_pipeline.bat` einmal täglich (z.B. 08:00).

---

## Anforderungen (Setup)

- Python 3.12 + `pip install -r requirements.txt`
- `playwright install chromium`
- Node.js 20+ für Dashboard
- Google PageSpeed API Key (kostenlos): console.cloud.google.com → PageSpeed Insights API aktivieren
- Anthropic API Key (bereits vorhanden vom Stash-Projekt)
- `.env` Datei:
  ```
  ANTHROPIC_API_KEY=sk-ant-...
  GOOGLE_API_KEY=AIza...
  ```

---

## DSGVO-Hinweise

- Alle Daten verbleiben lokal auf dem Rechner
- Nur öffentlich zugängliche Geschäftsdaten werden gespeichert (kein Personenbezug von Privatpersonen)
- Cold Email an Businesses ist unter UWG §7 eine Grauzone — manuelles Freigeben + personalisierter Inhalt reduziert rechtliches Risiko
- Empfehlung: Datensätze nach 90 Tagen ohne Aktivität archivieren/löschen
- Keine Weitergabe an Dritte, kein Cloud-Upload

---

## MVP Scope

Dieses Spec beschreibt den MVP. Explizit ausgeschlossen:
- Loom Video Modul (Phase 2)
- Multi-User Support (Phase 2)
- PostgreSQL Migration (Phase 2)
- Automatischer Email-Versand ohne manuelle Freigabe (nie, aus rechtlichen Gründen)
- LinkedIn/Instagram Scraping (Phase 2, API-Restriktionen)

---

## Kostenschätzung (monatlich)

| Komponente | Kosten |
|---|---|
| Claude Haiku (50 Emails/Tag × 30 Tage) | ~$1.50–3.00 |
| Google PageSpeed API | $0 (kostenlos) |
| Playwright/Scraping | $0 |
| Infrastruktur (lokal) | $0 |
| **Total** | **~$2–3/Monat** |
