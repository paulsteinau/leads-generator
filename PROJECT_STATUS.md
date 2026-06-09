# Berlin Leads — Project Status

Last updated: 2026-06-09

---

## What's been built and is working

- Full pipeline: Google Maps scrape → analyze → score → scrape website → generate React demo → deploy to Vercel → review in dashboard → approve → email
- React demo generator: Vite 6 + React 18 + Tailwind v4 + motion/react + GSAP + @phosphor-icons/react
- Claude Sonnet 4-6 generates a complete App.jsx (20k token budget, vision-enabled — sees screenshot of existing site)
- 6 design skill files bundled into repo and injected into every generation call
- Prompt caching enabled on all Claude calls (system prompt cached = cheaper on batch runs)
- `pipeline/redeploy_demo.py` — rebuild + redeploy a demo after manual edits to App.jsx

---

## Fixed this session (already in code)

| File | What changed |
|---|---|
| `pipeline/react-template/package.json` | Added `@phosphor-icons/react` (was missing — every build would fail) |
| `nixpacks.toml` | Added `node` provider + `npm install -g vercel` (Vercel CLI now available on Railway) |
| `pipeline/generator/demo.py` | Fixed Vercel cwd bug (`dist_dir` → `demo_dir`, uses `vercel deploy dist`) |
| `pipeline/generator/demo.py` | Fixed DB update: deploy failure now sets `stage='demo_deploy_failed'` instead of writing NULL demo_url and marking ready_for_review |
| `pipeline/generator/demo.py` | Raised `max_tokens` 16000 → 20000 (agents estimated 18-22k needed for full quality) |
| `.gitignore` | Added `pipeline/react-template/node_modules/` and `pipeline/react-template/dist/` |
| `pipeline/utils/skill_loader.py` | Now reads all 6 SKILL.md files dynamically + appends with AUTOMATION OVERRIDE to prevent meta-commentary in JSX output |
| `pipeline/utils/claude_p.py` | Added prompt caching (`cache_control: ephemeral` on system prompt) |
| `pipeline/redeploy_demo.py` | New script: rebuild + redeploy after editing App.jsx locally |
| `pipeline/sender/send.py` | Added logging, RESEND_FROM validation, 3-attempt retry with backoff |
| `pipeline/scraper/google_maps.py` | headless=True, removed --window-position (Railway compatible) |
| `api/main.py` | Bearer token auth middleware (API_SECRET env var), email.opened no longer sets status='replied' |
| `api/models.py` | LeadDetail now includes demo_url, description, audit_score, qualification, industry_tag, email_subjects, demo_screenshots |
| `api/db.py` | Added index on leads.email_message_id for fast webhook lookups |
| `pipeline/researcher/inspiration.py` | Switched to Haiku (4x cheaper), added 7-day DB cache per category |

---

## Still broken — CRITICAL (fix before going live)

All 5 CRITICALs fixed. See "Fixed this session" below.

---

## Still broken — WARN (fix after launch)

### Scraper
- `[:n]` slice always favors the same category/district combos — some combos may never run (`pipeline/scraper/google_maps.py`)
- Scroll depth fixed at 3× — misses results for popular categories
- Phone regex `[\+\(]?[\d\s\-\(\)]{7,20}` too greedy — matches zip codes, dates, price ranges; first match wins
- `www` vs non-www not caught by URL deduplicator — same business can be scraped twice
- Bare `except: continue` in Maps card loop — scraping errors produce zero output and no log

### Analyzer / Scorer
- PageSpeed API returning `None` causes score inflation — no slow-mobile flag applied, lead looks better than it is
- `"custom" CMS penalty` is dead code — condition `"custom" in cms` never matches `"wordpress"` etc.
- `has_linkedin` is extracted and saved to DB but never used in scoring
- `analyze_social` swallows all exceptions — network failure is indistinguishable from "no social presence"
- `email.opened` webhook event mapped to `status='replied'` — semantically wrong, inflates replied stats

### Email generation
- Demo URL is appended as a raw text block, not woven into the email copy (leads get a worse pitch)
- Subject line is only parsed from variant A — variant B always reuses A's subject
- No retry on transient Resend timeouts — one timeout = permanent skip, no record
- No bounce/complaint webhook handling — Resend can report bounces but nothing consumes them
- No `reply-to` field set — replies go to the `from` address

### API / DB
- No index on `leads.email_message_id` — webhook lookups do full table scan as volume grows
- `LeadDetail` Pydantic model missing `demo_url`, `audit_score`, `description`, `qualification` — dashboard detail can't display them without changes
- `/approve-email` writes to `leads` and `email_log` without a transaction — if second INSERT fails, leads table is already updated and log entry is missing
- Migration errors silently swallowed (`except Exception: pass`) — app can boot in broken state
- `get_conn()` not closed in several endpoints — connection leak under load

### Researcher
- No caching — Sonnet API call on every demo generation, even for repeated categories
- Model overkill — Haiku produces identical inspiration output at 4× lower cost
- Fake reference URLs in inspiration prompt (e.g. `zahnarzt-charlottenburg.de`) add false confidence — Claude can't visit them, they serve no purpose

### Dashboard
- Screenshots rendered as raw `<code>` text with file paths — completely invisible, should be `<img>` tags
- `status=pending_review` filter sends wrong stage name to backend (backend uses `ready_for_review`) — likely returns 0 results
- CSV export URL hardcoded to `localhost:8000` — breaks in production
- Edited email body in `ReviewPanel` textarea is local state only — backend still sends original `email_body_a` on approve
- Notes field exists in DB but no UI input to write notes on detail page
- "Uncontactable" CRM status missing from `EmailPanel` status buttons

---

## Cost structure

At 20 demos/day (600/month):

| Item | Cost/month |
|---|---|
| Demo generation — Claude Sonnet 4-6 (32k input, 20k output) | ~$240 |
| Email generation — Claude Haiku | ~$3 |
| Inspiration — Claude Sonnet (currently, should be Haiku) | ~$7 |
| Railway (API + pipeline compute) | ~$20 |
| Railway persistent volume (~5GB) | ~$2 |
| Vercel Pro (unlimited demo deployments) | $20 |
| Resend | $0 (3k emails/month free) |
| Google PageSpeed API | $0 (free tier) |
| **Total** | **~$292/month** |

At 10 demos/day: ~$165/month.

### Available cost reductions (no quality impact)

| Optimization | Saving | Effort |
|---|---|---|
| Prompt caching on system prompt (DONE) | ~$48/month | Done |
| Switch inspiration to Haiku | ~$7/month | 1 line |
| Add DB cache for inspiration (per category) | ~$0 additional | 15 min |
| **Total available savings** | **~$55/month** | |

After optimizations: ~$237/month at 20 demos/day.

The output tokens (20k at $15/M = $0.30/demo) are the irreducible cost of quality — can't compress.

---

## What needs to happen before Railway deployment

### You do (account setup)
1. Create Railway service, attach persistent volume at `/data`
2. Set env vars on Railway:
   - `ANTHROPIC_API_KEY`
   - `RESEND_API_KEY`
   - `RESEND_FROM` (verified sending domain, e.g. `noreply@yourdomain.com`)
   - `VERCEL_TOKEN` (from vercel.com/account/tokens)
   - `DATA_DIR=/data`
   - `API_SECRET` (any random string — used as bearer token)
3. Push repo to Railway (connect GitHub repo)
4. Deploy dashboard: `cd dashboard && vercel --prod`

### I do (code fixes — next session)
In priority order:
1. Wire Resend into `/approve` endpoint — core workflow
2. Add error logging + basic retry to email sender
3. Fix scraper `headless=True`
4. Add bearer token auth to API
5. Switch inspiration to Haiku + add DB cache
6. Fix screenshots as `<img>` in dashboard
7. Fix `pending_review` filter typo in dashboard
8. Fix CSV export hardcoded localhost URL
9. Add `email_message_id` DB index
10. Expand `LeadDetail` model to include `demo_url`, `audit_score`, etc.
11. Fix `email.opened` → `status='replied'` wrong mapping
12. Add transaction to `/approve-email` write
13. Fix phone regex (too greedy)
14. Fix `www` vs non-www deduplication
15. Fix "custom" CMS penalty dead code
16. Wire demo URL into email copy

---

## Edit workflow (after Railway is live)

```
# Generate demo for a specific lead
python pipeline/generate_demo_single.py <lead_id>

# Open and edit in Claude Code
# → data/demos/{slug}/src/App.jsx

# Rebuild + redeploy after edits
python pipeline/redeploy_demo.py <lead_id>
```

The new URL appears in the dashboard automatically after `redeploy_demo.py`.
