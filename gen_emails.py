import json
import os
from dotenv import load_dotenv
load_dotenv()

from api.db import get_conn
from pipeline.emailgen.generator import generate_emails

conn = get_conn()
leads = [dict(r) for r in conn.execute(
    "SELECT * FROM leads WHERE stage='scored' AND lead_tier IN ('hot','warm')"
).fetchall()]

print(f"{len(leads)} Leads gefunden")
for lead in leads:
    emails = generate_emails(lead, conn)
    if emails:
        conn.execute(
            "UPDATE leads SET email_subject=?,email_body_a=?,email_body_b=?,"
            "stage='email_ready',updated_at=datetime('now') WHERE id=?",
            (emails["subject"], emails["body_a"], emails["body_b"], lead["id"]),
        )
        print(f"  Email generiert: {lead['name']}")
    else:
        conn.execute(
            "UPDATE leads SET stage='email_ready',updated_at=datetime('now') WHERE id=?",
            (lead["id"],),
        )
        print(f"  Kein Email: {lead['name']}")
    conn.commit()

print("Fertig!")
