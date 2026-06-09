# pipeline/redeploy_demo.py
"""
Rebuild and redeploy a demo after manual edits to App.jsx.
Usage: python pipeline/redeploy_demo.py <lead_id>

Workflow:
  1. Edit data/demos/{slug}/src/App.jsx in Claude Code
  2. Run this script — it rebuilds with Vite and redeploys to Vercel
  3. Dashboard URL updates automatically
"""
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from api.db import get_conn
from pipeline.generator.demo import DATA_DIR, _make_slug, _build_react, _deploy_to_vercel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def redeploy(lead_id: int) -> str | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    if not row:
        log.error(f"Lead {lead_id} not found")
        return None

    lead = dict(row)
    slug = _make_slug(lead)
    demo_dir = DATA_DIR / slug

    if not (demo_dir / "src" / "App.jsx").exists():
        log.error(f"App.jsx not found at {demo_dir / 'src' / 'App.jsx'}")
        log.error("Run generate_demo_single.py first, or check that DATA_DIR is correct.")
        return None

    log.info(f"Building {slug}...")
    build_ok = _build_react(demo_dir)
    if not build_ok:
        log.error("Vite build failed — check App.jsx for syntax errors")
        return None

    log.info("Deploying to Vercel...")
    demo_url = _deploy_to_vercel(demo_dir, slug)

    if demo_url:
        conn.execute(
            "UPDATE leads SET demo_url=?, demo_generated_at=datetime('now'),"
            " stage='ready_for_review', updated_at=datetime('now') WHERE id=?",
            (demo_url, lead_id),
        )
        conn.commit()
        log.info(f"Done: {demo_url}")
    else:
        log.error("Vercel deploy failed — URL not captured. Check VERCEL_TOKEN env var.")

    conn.close()
    return demo_url


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python pipeline/redeploy_demo.py <lead_id>")
        sys.exit(1)
    result = redeploy(int(sys.argv[1]))
    sys.exit(0 if result else 1)
