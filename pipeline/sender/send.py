# pipeline/sender/send.py
"""
Sends a cold outreach email via Resend with the demo URL embedded.
"""
import os
from urllib.parse import urlparse


def send_email(lead: dict, conn) -> bool:
    """
    Send the approved email for a lead via Resend.
    Returns True on success, False on failure.
    """
    try:
        import resend  # type: ignore
        resend.api_key = os.environ.get("RESEND_API_KEY", "")
        if not resend.api_key:
            return False

        to_email = lead.get("email")
        if not to_email:
            return False

        # Check suppression list
        domain = to_email.split("@")[-1] if "@" in to_email else ""
        suppressed = conn.execute(
            "SELECT 1 FROM suppressions WHERE email=? OR domain=?",
            (to_email, domain),
        ).fetchone()
        if suppressed:
            return False

        subject = lead.get("email_subject") or "Ihre neue Website — kostenlose Demo"
        body = lead.get("email_body_a") or lead.get("email_body_b") or ""

        # Inject demo URL into body if present
        demo_url = lead.get("demo_url")
        if demo_url and demo_url not in body:
            body += f"\n\nHier können Sie Ihre Demo-Website ansehen:\n{demo_url}\n"

        # Build HTML version
        body_html = body.replace("\n", "<br>")
        if demo_url:
            body_html += (
                f'<br><br><a href="{demo_url}" '
                f'style="background:#2563eb;color:white;padding:12px 24px;'
                f'border-radius:6px;text-decoration:none;font-weight:bold;">'
                f'Demo ansehen →</a>'
            )

        params = {
            "from": os.environ.get("RESEND_FROM", "demo@yourdomain.com"),
            "to": [to_email],
            "subject": subject,
            "text": body,
            "html": f"<html><body style='font-family:sans-serif;max-width:600px;margin:0 auto'>{body_html}</body></html>",
        }

        response = resend.Emails.send(params)
        msg_id = response.get("id") if isinstance(response, dict) else getattr(response, "id", None)

        if msg_id:
            domain_for_log = urlparse(lead.get("website", "")).netloc or domain
            conn.execute(
                "INSERT INTO email_log (lead_id, domain, sent_at, subject, body)"
                " VALUES (?,?,datetime('now'),?,?)",
                (lead["id"], domain_for_log, subject, body),
            )
            conn.execute(
                "UPDATE leads SET email_message_id=?, status='contacted',"
                " updated_at=datetime('now') WHERE id=?",
                (msg_id, lead["id"]),
            )
            conn.commit()
            return True

        return False

    except Exception:
        return False
