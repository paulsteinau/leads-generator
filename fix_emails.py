import sqlite3
conn = sqlite3.connect('data/leads.db')
n = conn.execute("UPDATE leads SET stage='scored' WHERE stage='email_ready' AND email_body_a IS NULL AND lead_tier IN ('hot','warm')").rowcount
conn.commit()
print(f"Zurueckgesetzt: {n} Leads")
