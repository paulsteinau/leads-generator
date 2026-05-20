import json
import os
from datetime import datetime, timedelta
from urllib.parse import urlparse
import anthropic

SYSTEM = (
    "Du bist ein professioneller Web-Berater in Berlin. "
    "Schreibe ausschliesslich auf Deutsch. Maximal 150 Woerter. "
    "Keine Agentur-Buzzwords, keine Gedankenstriche. "
    "Nutze konkrete Zahlen aus den Analysedaten."
)

# Haiku pricing per token
INPUT_COST_PER_TOKEN = 0.80 / 1_000_000
OUTPUT_COST_PER_TOKEN = 4.00 / 1_000_000


def _context(lead: dict) -> str:
    flags = json.loads(lead.get("red_flags") or "[]")
    return "\n".join([
        f"Firma: {lead.get('name', '?')}",
        f"Branche: {lead.get('category', '?')}",
        f"Bezirk: {lead.get('district', 'Berlin')}",
        f"Google: {lead.get('google_reviews', '?')} Bewertungen, {lead.get('google_rating', '?')}",
        f"Website: {lead.get('website') or 'keine'}",
        f"Mobile PageSpeed: {lead.get('pagespeed_mobile', '?')}/100",
        f"CMS: {lead.get('cms_detected', '?')}",
        f"Probleme: {', '.join(flags) or 'keine'}",
    ])


def _cooldown(conn, website: str | None, days: int = 90) -> bool:
    if not website:
        return False
    domain = urlparse(website).netloc
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    return conn.execute(
        "SELECT 1 FROM email_log WHERE domain=? AND sent_at>?", (domain, cutoff)
    ).fetchone() is not None


def _log_cost(conn, lead_id: int, input_tokens: int, output_tokens: int):
    cost = (input_tokens * INPUT_COST_PER_TOKEN) + (output_tokens * OUTPUT_COST_PER_TOKEN)
    conn.execute(
        "INSERT INTO cost_log (lead_id, input_tokens, output_tokens, cost_usd) VALUES (?,?,?,?)",
        (lead_id, input_tokens, output_tokens, round(cost, 6)),
    )
    conn.commit()


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
        subject = "Ihre Online-Praesenz in Berlin"
        body = raw.strip()
    return subject, body


def generate_emails(lead: dict, conn, dry_run: bool = False) -> dict | None:
    if not lead.get("email"):
        return None
    if _cooldown(conn, lead.get("website")):
        return None

    if dry_run:
        return {
            "subject": f"[DRY RUN] {lead.get('name', '?')}",
            "body_a": "[DRY RUN] Variante A",
            "body_b": "[DRY RUN] Variante B",
        }

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    ctx = _context(lead)
    lead_id = lead.get("id", 0)
    total_in, total_out = 0, 0

    def call(instruction: str) -> str:
        nonlocal total_in, total_out
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=SYSTEM,
            messages=[{"role": "user", "content":
                f"Outreach-Email:\n\n{ctx}\n\nAnsatz: {instruction}\n\n"
                f"Format:\nBetreff: [Betreff]\n\n[Email-Text]"}],
        )
        total_in += resp.usage.input_tokens
        total_out += resp.usage.output_tokens
        return resp.content[0].text

    subj, body_a = _parse(call("Konkrete Probleme und deren Auswirkung auf Kunden nennen."))
    _, body_b = _parse(call("Verpasstes Potenzial und Wachstumschance betonen."))

    _log_cost(conn, lead_id, total_in, total_out)

    return {"subject": subj, "body_a": body_a, "body_b": body_b}
