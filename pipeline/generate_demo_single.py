# pipeline/generate_demo_single.py
"""
Entry script: run the full demo generation pipeline for a single lead.
Usage: python pipeline/generate_demo_single.py <lead_id>
"""
import re
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from api.db import get_conn
from pipeline.generator.demo import generate_demo, _make_slug
from pipeline.generator.screenshots import capture_demo_screenshots
from pipeline.emailgen.generator import generate_emails

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def run(lead_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    if not row:
        log.error(f"Lead {lead_id} not found")
        return

    lead = dict(row)
    log.info(f"Generating demo for lead {lead_id}: {lead.get('name')}")

    # Mark as in-progress
    conn.execute(
        "UPDATE leads SET stage='generating_demo', updated_at=datetime('now') WHERE id=?",
        (lead_id,),
    )
    conn.commit()

    try:
        demo_url = generate_demo(lead, conn)
        log.info(f"Demo generated: {demo_url}")

        if demo_url:
            slug = _make_slug(lead)
            paths = capture_demo_screenshots(demo_url, slug, conn, lead_id)
            log.info(f"Screenshots: {len(paths)} captured")

            # Generate email after demo is ready
            lead = dict(conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone())
            log.info("Generating email copy...")
            emails = generate_emails(lead, conn)
            if emails:
                conn.execute(
                    "UPDATE leads SET email_subject=?,email_body_a=?,email_body_b=?,"
                    "stage='ready_for_review',updated_at=datetime('now') WHERE id=?",
                    (emails["subject"], emails["body_a"], emails["body_b"], lead_id),
                )
            else:
                conn.execute(
                    "UPDATE leads SET stage='ready_for_review',updated_at=datetime('now') WHERE id=?",
                    (lead_id,),
                )
            conn.commit()
            log.info("Phase 2 complete — lead is ready for review")
        else:
            log.warning("Demo URL is None — Vercel deploy may have failed")
            conn.execute(
                "UPDATE leads SET stage='demo_failed', updated_at=datetime('now') WHERE id=?",
                (lead_id,),
            )
            conn.commit()

    except Exception as e:
        log.error(f"Demo generation failed: {e}", exc_info=True)
        conn.execute(
            "UPDATE leads SET stage='demo_failed', updated_at=datetime('now') WHERE id=?",
            (lead_id,),
        )
        conn.commit()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pipeline/generate_demo_single.py <lead_id>")
        sys.exit(1)
    run(int(sys.argv[1]))
