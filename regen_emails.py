import os
from dotenv import load_dotenv
load_dotenv()

from api.db import get_conn
from pipeline.emailgen.generator import generate_emails

conn = get_conn()
leads = [dict(r) for r in conn.execute(
    "SELECT * FROM leads WHERE lead_tier IN ('hot','warm') AND stage='email_ready'"
).fetchall()]

print(f"{len(leads)} Leads werden neu generiert...")
for lead in leads:
    emails = generate_emails(lead, conn)
    if emails:
        conn.execute(
            "UPDATE leads SET email_subject=?,email_body_a=?,email_body_b=?,"
            "updated_at=datetime('now') WHERE id=?",
            (emails["subject"], emails["body_a"], emails["body_b"], lead["id"]),
        )
        print(f"  {lead['name']}")
    conn.commit()

print("Fertig!")
