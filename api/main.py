import json
import csv
import io
import os
import secrets
import sys
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from api.db import get_conn, init_db
from api.models import (
    LeadSummary, LeadDetail, StatsResponse,
    ApproveEmailRequest, UpdateStatusRequest, UpdateEmailRequest,
    PendingReviewLead, RegenerateRequest, EditDemoRequest,
    ResendWebhookPayload, UnsubscribeRequest, ManualLeadRequest,
)

app = FastAPI(title="Berlin Lead-Gen API")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost:\d+|.*\.vercel\.app)",
    allow_methods=["*"],
    allow_headers=["*"],
)

# Endpoints that must remain public (Resend sends no auth header)
_PUBLIC_PATHS = {"/webhook/resend", "/unsubscribe"}


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # CORS preflight must pass through so the browser gets Allow headers
    if request.method == "OPTIONS":
        return await call_next(request)
    secret = os.environ.get("API_SECRET", "")
    if not secret or request.url.path in _PUBLIC_PATHS:
        return await call_next(request)
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    if not token or not secrets.compare_digest(token, secret):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return await call_next(request)

ROOT = Path(__file__).parent.parent
LOG_FILE = ROOT / "pipeline.log"
_pipeline_proc: subprocess.Popen | None = None


@app.on_event("startup")
def startup():
    conn = init_db()
    # Any lead stuck in generating_demo from a previous container run is a zombie — reset it
    affected = conn.execute(
        "UPDATE leads SET stage='demo_build_failed', demo_sub_stage=NULL, updated_at=datetime('now')"
        " WHERE stage='generating_demo'"
    ).rowcount
    conn.commit()
    if affected:
        print(f"[startup] Reset {affected} zombie generating_demo lead(s) to demo_build_failed")


# ── Pipeline control ──────────────────────────────────────────────────────────

@app.post("/pipeline/start")
def pipeline_start(dry_run: bool = False):
    global _pipeline_proc
    if _pipeline_proc and _pipeline_proc.poll() is None:
        return {"ok": False, "error": "Already running", "pid": _pipeline_proc.pid}
    cmd = [sys.executable, str(ROOT / "pipeline" / "run.py")]
    if dry_run:
        cmd.append("--dry-run")
    _pipeline_proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )
    return {"ok": True, "pid": _pipeline_proc.pid}


@app.post("/pipeline/stop")
def pipeline_stop():
    global _pipeline_proc
    if not _pipeline_proc or _pipeline_proc.poll() is not None:
        return {"ok": False, "error": "Not running"}
    _pipeline_proc.terminate()
    return {"ok": True}


@app.get("/pipeline/status")
def pipeline_status():
    if not _pipeline_proc:
        return {"running": False, "pid": None}
    running = _pipeline_proc.poll() is None
    return {"running": running, "pid": _pipeline_proc.pid if running else None}


@app.get("/pipeline/logs")
def pipeline_logs(lines: int = 100):
    if not LOG_FILE.exists():
        return {"lines": []}
    text = LOG_FILE.read_text(encoding="utf-8", errors="replace")
    all_lines = text.splitlines()
    return {"lines": all_lines[-lines:]}


# ── Costs ────────────────────────────────────────────────────────────────────

@app.get("/costs")
def get_costs():
    conn = get_conn()
    today = datetime.now().strftime("%Y-%m-%d")
    month_start = datetime.now().strftime("%Y-%m-01")

    def s(q, *p):
        return conn.execute(q, p).fetchone()[0] or 0

    # Per-model breakdown
    by_model_rows = conn.execute(
        "SELECT model, SUM(cost_usd), COUNT(*) FROM cost_log GROUP BY model ORDER BY SUM(cost_usd) DESC"
    ).fetchall()
    by_model = [{"model": r[0], "total_usd": round(r[1] or 0, 4), "calls": r[2]} for r in by_model_rows]

    # Cost per demo: sum of demo_gen + design_brief + content_extraction per lead, then average
    demo_cost_row = conn.execute(
        "SELECT AVG(lead_cost) FROM ("
        "  SELECT lead_id, SUM(cost_usd) AS lead_cost FROM cost_log"
        "  WHERE stage IN ('demo_gen','design_brief','content_extraction')"
        "  GROUP BY lead_id"
        ")"
    ).fetchone()
    cost_per_demo = round(demo_cost_row[0] or 0, 4)

    demos_total = s(
        "SELECT COUNT(DISTINCT lead_id) FROM cost_log WHERE stage='demo_gen'"
    )

    return {
        "today_usd": round(s("SELECT SUM(cost_usd) FROM cost_log WHERE logged_at >= ?", today), 4),
        "month_usd": round(s("SELECT SUM(cost_usd) FROM cost_log WHERE logged_at >= ?", month_start), 4),
        "total_usd": round(s("SELECT SUM(cost_usd) FROM cost_log"), 4),
        "demos_total": demos_total,
        "cost_per_demo_avg": cost_per_demo,
        "by_model": by_model,
        "today_tokens_in": s("SELECT SUM(input_tokens) FROM cost_log WHERE logged_at >= ?", today),
        "today_tokens_out": s("SELECT SUM(output_tokens) FROM cost_log WHERE logged_at >= ?", today),
    }


# ── Stats ─────────────────────────────────────────────────────────────────────

@app.get("/stats", response_model=StatsResponse)
def get_stats():
    conn = get_conn()
    today = datetime.now().strftime("%Y-%m-%d")

    def count(q, *p):
        return conn.execute(q, p).fetchone()[0]

    return StatsResponse(
        hot=count("SELECT COUNT(*) FROM leads WHERE lead_tier='hot'"),
        warm=count("SELECT COUNT(*) FROM leads WHERE lead_tier='warm'"),
        low=count("SELECT COUNT(*) FROM leads WHERE lead_tier='low'"),
        new_today=count("SELECT COUNT(*) FROM leads WHERE created_at >= ?", today),
        contacted=count("SELECT COUNT(*) FROM leads WHERE status='contacted'"),
        replied=count("SELECT COUNT(*) FROM leads WHERE status='replied'"),
    )


# ── Leads ─────────────────────────────────────────────────────────────────────

@app.get("/leads")
def list_leads(
    tier: str | None = None,
    district: str | None = None,
    category: str | None = None,
    stage: str | None = None,
) -> list[LeadSummary]:
    conn = get_conn()
    q = "SELECT * FROM leads WHERE 1=1"
    p: list = []
    for col, val in [("lead_tier", tier), ("district", district),
                     ("category", category), ("stage", stage)]:
        if val:
            q += f" AND {col}=?"
            p.append(val)
    q += " ORDER BY lead_score DESC"
    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    return [
        LeadSummary(
            id=r["id"], name=r["name"], category=r["category"],
            district=r["district"], lead_score=r["lead_score"],
            lead_tier=r["lead_tier"], stage=r["stage"], status=r["status"],
            has_email=bool(r["email"]),
            follow_up_due=(r["status"] == "contacted" and (r["updated_at"] or "") < cutoff),
            created_at=r["created_at"] or "",
        )
        for r in conn.execute(q, p).fetchall()
    ]


@app.post("/leads/manual")
def create_manual_lead(body: ManualLeadRequest):
    from pipeline.scraper.deduplicator import url_hash, is_duplicate
    conn = get_conn()
    site = body.website or ""
    key = site if site else f"nw-{body.name}"
    if is_duplicate(conn, key):
        raise HTTPException(409, "Lead already exists")
    score = {"hot": 80, "warm": 55, "low": 30}.get(body.lead_tier, 55)
    conn.execute(
        "INSERT INTO leads (url_hash,name,category,district,phone,email,website,"
        "lead_score,lead_tier,stage,status,notes) VALUES (?,?,?,?,?,?,?,?,?,'scored','new',?)",
        (url_hash(key), body.name, body.category, body.district,
         body.phone, body.email, site or None,
         score, body.lead_tier, body.notes),
    )
    conn.commit()
    lead_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return {"ok": True, "id": lead_id}


@app.get("/leads/export")
def export_leads(tier: str | None = None):
    conn = get_conn()
    q = "SELECT * FROM leads" + (" WHERE lead_tier=?" if tier else "")
    rows = conn.execute(q, [tier] if tier else []).fetchall()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["id", "name", "category", "district", "email", "phone",
                "website", "lead_score", "lead_tier", "status", "created_at"])
    for r in rows:
        w.writerow([r["id"], r["name"], r["category"], r["district"], r["email"],
                    r["phone"], r["website"], r["lead_score"], r["lead_tier"],
                    r["status"], r["created_at"]])
    out.seek(0)
    return StreamingResponse(
        iter([out.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"},
    )


@app.get("/leads/pending-review")
def list_pending_review():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, name, demo_url, created_at FROM leads WHERE stage='ready_for_review'"
        " ORDER BY created_at DESC"
    ).fetchall()
    leads = [
        PendingReviewLead(
            id=r["id"],
            name=r["name"],
            demo_url=r["demo_url"],
            created_at=r["created_at"] or "",
        )
        for r in rows
    ]
    return {"count": len(leads), "leads": leads}


@app.get("/leads/{lead_id}", response_model=LeadDetail)
def get_lead(lead_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Lead not found")
    d = dict(row)
    d["red_flags"] = json.loads(d.get("red_flags") or "[]")
    for k in ["has_instagram", "has_facebook", "has_linkedin", "email_approved"]:
        d[k] = bool(d.get(k))
    for k in ["has_ssl", "has_cta", "has_booking", "is_mobile_ready"]:
        d[k] = bool(d[k]) if d.get(k) is not None else None
    d["updated_at"] = d.get("updated_at") or ""
    return LeadDetail(**d)


@app.post("/leads/{lead_id}/approve-email")
def approve_email(lead_id: int, body: ApproveEmailRequest):
    if body.variant not in ("a", "b"):
        raise HTTPException(400, "variant must be 'a' or 'b'")
    from urllib.parse import urlparse
    conn = get_conn()
    row = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Lead not found")
    conn.execute(
        "UPDATE leads SET email_approved=1, email_variant=?, status='contacted',"
        " updated_at=datetime('now') WHERE id=?",
        (body.variant, lead_id),
    )
    if row["website"]:
        domain = urlparse(row["website"]).netloc
        body_text = row["email_body_a"] if body.variant == "a" else row["email_body_b"]
        conn.execute(
            "INSERT INTO email_log (lead_id, domain, sent_at, subject, body)"
            " VALUES (?,?,datetime('now'),?,?)",
            (lead_id, domain, row["email_subject"] or "", body_text or ""),
        )
    conn.commit()
    return {"ok": True}


@app.post("/leads/{lead_id}/status")
def update_status(lead_id: int, body: UpdateStatusRequest):
    allowed = {"contacted", "replied", "closed", "ignored", "new"}
    if body.status not in allowed:
        raise HTTPException(400, f"status must be one of {allowed}")
    conn = get_conn()
    conn.execute(
        "UPDATE leads SET status=?, updated_at=datetime('now') WHERE id=?",
        (body.status, lead_id),
    )
    conn.commit()
    return {"ok": True}


@app.post("/leads/{lead_id}/email")
def update_email(lead_id: int, body: UpdateEmailRequest):
    email = (body.email or "").strip() or None
    conn = get_conn()
    conn.execute(
        "UPDATE leads SET email=?, updated_at=datetime('now') WHERE id=?",
        (email, lead_id),
    )
    conn.commit()
    return {"ok": True}


# ── Review / Approval ─────────────────────────────────────────────────────────

@app.post("/leads/{lead_id}/approve")
def approve_lead(lead_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Lead not found")
    conn.execute(
        "UPDATE leads SET stage='approved', updated_at=datetime('now') WHERE id=?",
        (lead_id,),
    )
    conn.execute(
        "INSERT INTO admin_actions (lead_id, action, payload) VALUES (?,?,?)",
        (lead_id, "approved", None),
    )
    conn.commit()

    lead = dict(conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone())
    from pipeline.sender.send import send_email  # noqa: PLC0415
    try:
        sent = send_email(lead, conn)
    except Exception:
        sent = False
    if not sent:
        return {"ok": False, "error": "send failed"}
    return {"ok": True, "sent": sent}


@app.post("/leads/{lead_id}/reject")
def reject_lead(lead_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Lead not found")
    conn.execute(
        "UPDATE leads SET stage='rejected', updated_at=datetime('now') WHERE id=?",
        (lead_id,),
    )
    conn.execute(
        "INSERT INTO admin_actions (lead_id, action, payload) VALUES (?,?,?)",
        (lead_id, "rejected", None),
    )
    conn.commit()
    return {"ok": True}


@app.post("/leads/{lead_id}/regenerate")
def regenerate_lead(lead_id: int, body: RegenerateRequest):
    conn = get_conn()
    row = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Lead not found")

    iteration_count = conn.execute(
        "SELECT COUNT(*) FROM admin_actions WHERE lead_id=? AND action='regenerated'",
        (lead_id,),
    ).fetchone()[0]

    if iteration_count >= 3:
        conn.execute(
            "UPDATE leads SET stage='needs_manual_completion', updated_at=datetime('now')"
            " WHERE id=?",
            (lead_id,),
        )
        conn.commit()
        return {"ok": False, "error": "max iterations reached"}

    lead = dict(row)
    from pipeline.generator.demo import generate_demo  # noqa: PLC0415
    slug = generate_demo(lead, conn)

    conn.execute(
        "INSERT INTO admin_actions (lead_id, action, payload) VALUES (?,?,?)",
        (lead_id, "regenerated", body.instructions),
    )
    conn.commit()
    return {"ok": True, "slug": slug}


@app.post("/leads/{lead_id}/edit-demo")
def edit_demo(lead_id: int, body: EditDemoRequest):
    conn = get_conn()
    row = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Lead not found")

    iteration_count = conn.execute(
        "SELECT COUNT(*) FROM admin_actions WHERE lead_id=? AND action IN ('regenerated','edited')",
        (lead_id,),
    ).fetchone()[0]

    if iteration_count >= 3:
        return {"ok": False, "error": "max iterations reached"}

    lead = dict(row)
    slug = lead.get("demo_url", "").rstrip("/").rsplit("/", 1)[-1] if lead.get("demo_url") else ""

    ROOT_PATH = Path(__file__).parent.parent
    content_path = ROOT_PATH / "data" / "demos" / slug / "content.json"
    if not content_path.exists():
        raise HTTPException(404, "Demo content not found")

    existing_content = json.loads(content_path.read_text(encoding="utf-8"))

    from pipeline.utils.claude_p import claude_p  # noqa: PLC0415
    prompt = (
        f"Du bearbeitest den Inhalt einer Demo-Website für '{lead.get('name', '')}'.\n"
        f"Bestehender Inhalt (JSON):\n{json.dumps(existing_content, ensure_ascii=False, indent=2)}\n\n"
        f"Anweisung des Nutzers: {body.description}\n\n"
        "Gib NUR das vollständige, überarbeitete JSON-Objekt zurück. Kein Markdown, keine Erklärungen."
    )
    result = claude_p(prompt, model="claude-haiku-4-5", lead_id=lead_id, stage="edit_demo")

    try:
        new_content = json.loads(result)
    except json.JSONDecodeError:
        raise HTTPException(500, "LLM returned invalid JSON")

    content_path.write_text(json.dumps(new_content, ensure_ascii=False, indent=2), encoding="utf-8")

    conn.execute(
        "INSERT INTO admin_actions (lead_id, action, payload) VALUES (?,?,?)",
        (lead_id, "edited", body.description),
    )
    conn.commit()
    return {"ok": True}


# ── Demo Generation ───────────────────────────────────────────────────────────

@app.post("/leads/{lead_id}/generate-demo")
def trigger_generate_demo(lead_id: int):
    conn = get_conn()
    row = conn.execute("SELECT stage FROM leads WHERE id=?", (lead_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Lead not found")
    if row["stage"] in ("generating_demo",):
        return {"ok": False, "error": "Already generating"}

    import sys, os
    cmd = [
        sys.executable,
        str(ROOT / "pipeline" / "generate_demo_single.py"),
        str(lead_id),
    ]
    subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )
    return {"ok": True, "lead_id": lead_id}


@app.get("/leads/{lead_id}/demo-status")
def demo_status(lead_id: int):
    conn = get_conn()
    row = conn.execute(
        "SELECT stage, demo_url, demo_screenshots, demo_sub_stage FROM leads WHERE id=?", (lead_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Lead not found")
    return {
        "stage": row["stage"],
        "sub_stage": row["demo_sub_stage"],
        "demo_url": row["demo_url"],
        "has_screenshots": bool(row["demo_screenshots"]),
        "ready": row["stage"] == "ready_for_review",
        "failed": row["stage"] == "demo_failed",
    }


# ── Webhooks ──────────────────────────────────────────────────────────────────

@app.post("/webhook/resend")
def webhook_resend(body: ResendWebhookPayload):
    conn = get_conn()
    event_type = body.type
    data = body.data or {}

    if event_type == "email.bounced":
        recipient = data.get("to") or data.get("email") or ""
        domain = recipient.split("@")[-1] if "@" in recipient else None
        message_id = data.get("email_id") or data.get("id")
        conn.execute(
            "INSERT OR IGNORE INTO suppressions (email, domain, reason) VALUES (?,?,?)",
            (recipient or None, domain, "bounce"),
        )
        if message_id:
            conn.execute(
                "UPDATE leads SET stage='bounced', updated_at=datetime('now')"
                " WHERE email_message_id=?",
                (message_id,),
            )
    elif event_type == "email.delivered":
        message_id = data.get("email_id") or data.get("id")
        if message_id:
            conn.execute(
                "UPDATE leads SET status='contacted', updated_at=datetime('now')"
                " WHERE email_message_id=?",
                (message_id,),
            )
    elif event_type == "email.opened":
        message_id = data.get("email_id") or data.get("id")
        if message_id:
            conn.execute(
                "UPDATE leads SET notes='Email geöffnet',"
                " updated_at=datetime('now') WHERE email_message_id=?",
                (message_id,),
            )

    conn.commit()
    return {"ok": True}


@app.post("/unsubscribe")
def unsubscribe(body: UnsubscribeRequest):
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO suppressions (email, domain, reason) VALUES (?,?,?)",
        (body.email, body.domain, "opt_out"),
    )
    conn.commit()
    return {"ok": True}
