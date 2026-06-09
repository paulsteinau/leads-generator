"""
Migrate hot/warm leads from local DB to Railway.
Usage: python migrate_leads.py
"""
import json
import os
import sys
import httpx
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv()

from api.db import get_conn

RAILWAY_URL = "https://web-production-8e432.up.railway.app"
API_SECRET = os.environ.get("API_SECRET", "")

if not API_SECRET:
    print("ERROR: API_SECRET not set in .env")
    sys.exit(1)

conn = get_conn()
leads = conn.execute(
    "SELECT * FROM leads WHERE lead_tier IN ('hot','warm') ORDER BY lead_score DESC"
).fetchall()

print(f"Found {len(leads)} hot/warm leads — importing to Railway...")

ok, skipped, failed = 0, 0, 0
for row in leads:
    lead = dict(row)
    try:
        r = httpx.post(
            f"{RAILWAY_URL}/admin/import-lead",
            json=lead,
            headers={"Authorization": f"Bearer {API_SECRET}"},
            timeout=10,
        )
        result = r.json()
        if result.get("ok"):
            ok += 1
            print(f"  OK  {lead.get('name')} ({lead.get('lead_tier')})")
        else:
            skipped += 1
            print(f"  SKIP {lead.get('name')} — {result.get('reason')}")
    except Exception as e:
        failed += 1
        print(f"  FAIL {lead.get('name')} — {e}")

print(f"\nDone: {ok} imported, {skipped} skipped (duplicates), {failed} failed")
