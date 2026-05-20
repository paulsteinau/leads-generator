import json
import csv
import io
import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from api.db import get_conn, init_db
from api.models import (
    LeadSummary, LeadDetail, StatsResponse,
    ApproveEmailRequest, UpdateStatusRequest, UpdateEmailRequest,
)

app = FastAPI(title="Berlin Lead-Gen API")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://localhost:\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)

ROOT = Path(__file__).parent.parent
LOG_FILE = ROOT / "pipeline.log"
_pipeline_proc: subprocess.Popen | None = None


@app.on_event("startup")
def startup():
    init_db()


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

    return {
        "today_usd": round(s("SELECT SUM(cost_usd) FROM cost_log WHERE logged_at >= ?", today), 4),
        "month_usd": round(s("SELECT SUM(cost_usd) FROM cost_log WHERE logged_at >= ?", month_start), 4),
        "total_usd": round(s("SELECT SUM(cost_usd) FROM cost_log"), 4),
        "total_emails": s("SELECT COUNT(*) FROM cost_log"),
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
