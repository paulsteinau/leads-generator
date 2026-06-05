# Berlin Leads — Claude Code Context

## Design skill routing (MANDATORY for all website/UI work)

**Any time you build, modify, or generate a website, UI component, demo page, or HTML in this project — invoke ALL of these skills before writing code:**

| Trigger | Skills (invoke in order) |
|---|---|
| Generating any demo website or HTML | `design-taste-frontend` → `high-end-visual-design` → `emil-design-eng` → `full-output-enforcement` |
| Redesigning or improving a website | `redesign-existing-projects` → `design-taste-frontend` → `high-end-visual-design` |
| Any React/TSX/frontend component | `design-taste-frontend` → `emil-design-eng` |

Do not skip because "it's just a demo." These are non-negotiable.

**Pipeline automation:** `pipeline/utils/skill_loader.py` reads these SKILL.md files and injects their content as system prompt on every LLM call. Always keep that file up to date.

## Stack

- Python 3.12 (uv for dependencies)
- Playwright for scraping + screenshots
- SQLite with WAL (`data/leads.db`)
- FastAPI on port 8000
- Next.js 14 + Tailwind for dashboard on port 3000
- anthropic Python SDK for LLM calls (via `pipeline/utils/claude_p.py`)
- Vercel CLI for demo deployments
- Resend for email sending

## Commands

```bash
# API
uvicorn api.main:app --reload --port 8000

# Dashboard
cd dashboard && npm run dev

# Full pipeline
python pipeline/run.py

# Single demo generation
python pipeline/generate_demo_single.py <lead_id>

# Dry run
python pipeline/run.py --dry-run

# Tests
pytest tests/
```

## Architecture

```
pipeline/
  scraper/        — Google Maps + website content extraction
  analyzer/       — PageSpeed, SEO, UX, social
  extractor/      — Contact info extraction
  scorer/         — Lead scoring engine
  researcher/     — Category inspiration & design notes
  generator/      — Demo HTML generation + screenshots
  emailgen/       — Email copy generation (2 variants)
  sender/         — Resend email delivery
  utils/          — claude_p.py, skill_loader.py
  run.py          — Full pipeline runner
  generate_demo_single.py — Single-lead demo runner

api/              — FastAPI backend (port 8000)
  main.py         — All endpoints
  db.py           — Schema + migrations
  models.py       — Pydantic models

dashboard/        — Next.js frontend (port 3000)
  app/page.tsx    — Lead list + stats
  app/leads/[id]/ — Lead detail + demo + review + email

data/
  leads.db        — SQLite database
  demos/          — Generated demo HTML + screenshots per lead
```

## Rules

- Never commit API keys or tokens
- All LLM calls go through `pipeline/utils/claude_p.py`
- Schema changes: ALTER TABLE in `api/db.py` `_apply_migrations()`
- German copy in all user-facing text
- No Co-Authored-By in commits
