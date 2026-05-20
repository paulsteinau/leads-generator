import argparse
import asyncio
import json
import logging
import sys
from dotenv import load_dotenv

load_dotenv()

from api.db import init_db
from pipeline.scraper.search_queries import get_daily_queries
from pipeline.scraper.deduplicator import url_hash, is_duplicate
from pipeline.scraper.google_maps import scrape_google_maps
from pipeline.analyzer.seo import analyze_seo
from pipeline.analyzer.social import analyze_social
from pipeline.analyzer.website import analyze_pagespeed_batch
from pipeline.analyzer.ux import analyze_ux_batch
from pipeline.extractor.contact import extract_contacts_batch
from pipeline.scorer.engine import score_lead
from pipeline.emailgen.generator import generate_emails
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("pipeline.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def run(dry_run: bool = False):
    conn = init_db()
    c = {"new": 0, "hot": 0, "warm": 0, "low": 0, "uncontactable": 0, "skipped": 0}

    # Stage 1: Scrape
    queries = get_daily_queries(conn, n=22)
    log.info(f"Stage 1: {len(queries)} queries")
    raw: list[dict] = []

    for i, q in enumerate(queries):
        log.info(f"PROGRESS {i+1}/{len(queries)} {q['query']}")
        try:
            results = asyncio.run(scrape_google_maps(q["query"], max_results=15))
            for r in results:
                r["category"] = q["category"]
                r["district"] = q["district"]
            raw.extend(results)
            if not dry_run:
                conn.execute(
                    "INSERT INTO search_runs (query,district,category,results) VALUES (?,?,?,?)",
                    (q["query"], q["district"], q["category"], len(results)),
                )
                conn.commit()
        except Exception as e:
            log.error(f"Scrape error {q['query']}: {e}")

    # Deduplicate + insert
    for lead in raw:
        site = lead.get("website") or ""
        key = site if site else f"nw-{lead.get('name', '')}-{lead.get('address', '')}"
        if is_duplicate(conn, key):
            c["skipped"] += 1
            continue
        c["new"] += 1
        if not dry_run:
            h = url_hash(key)
            conn.execute(
                "INSERT INTO leads "
                "(url_hash,name,category,district,address,phone,website,google_rating,google_reviews)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (h, lead.get("name"), lead.get("category"), lead.get("district"),
                 lead.get("address"), lead.get("phone"), site or None,
                 lead.get("google_rating"), lead.get("google_reviews")),
            )
            conn.commit()

    log.info(f"New: {c['new']} | Skipped: {c['skipped']}")
    if dry_run:
        log.info("DRY RUN done.")
        return

    # Stage 2: Analyze
    pending = [dict(r) for r in conn.execute("SELECT * FROM leads WHERE stage='scraped'").fetchall()]
    with_site = [r for r in pending if r.get("website")]
    no_site = [r for r in pending if not r.get("website")]

    for lead in no_site:
        conn.execute(
            "UPDATE leads SET stage='analyzed', red_flags=? WHERE id=?",
            (json.dumps(["no_website"]), lead["id"]),
        )
    conn.commit()

    if with_site:
        log.info(f"Stage 2: {len(with_site)} websites")
        urls = [r["website"] for r in with_site]
        ps_results = asyncio.run(analyze_pagespeed_batch(urls))
        ux_results = asyncio.run(analyze_ux_batch(urls))

        for lead in tqdm(with_site, desc="Analyzing"):
            url = lead["website"]
            ps = ps_results.get(url, {})
            ux = ux_results.get(url, {})
            seo = analyze_seo(url)
            social = analyze_social(url)
            flags = list(set(
                ps.get("red_flags", []) + ux.get("red_flags", []) + seo.get("red_flags", [])
            ))
            conn.execute(
                "UPDATE leads SET "
                "pagespeed_mobile=?,pagespeed_desktop=?,has_ssl=?,cms_detected=?,"
                "has_cta=?,has_booking=?,is_mobile_ready=?,seo_score=?,"
                "has_instagram=?,has_facebook=?,has_linkedin=?,red_flags=?,"
                "stage='analyzed',updated_at=datetime('now') WHERE id=?",
                (ps.get("pagespeed_mobile"), ps.get("pagespeed_desktop"),
                 1 if seo.get("has_ssl") else 0, seo.get("cms_detected"),
                 1 if ux.get("has_cta") else 0, 1 if ux.get("has_booking") else 0,
                 1 if ux.get("is_mobile_ready") else 0, seo.get("seo_score"),
                 1 if social.get("has_instagram") else 0,
                 1 if social.get("has_facebook") else 0,
                 1 if social.get("has_linkedin") else 0,
                 json.dumps(flags), lead["id"]),
            )
        conn.commit()

    # Stage 3: Extract contacts
    to_extract = [dict(r) for r in conn.execute(
        "SELECT * FROM leads WHERE stage='analyzed'"
    ).fetchall()]
    if to_extract:
        log.info(f"Stage 3: {len(to_extract)} leads")
        contacts_map = asyncio.run(extract_contacts_batch(to_extract))
        for lead in tqdm(to_extract, desc="Extracting"):
            contacts = contacts_map.get(lead["id"], {"email": None, "phone": None})
            phone = contacts.get("phone") or lead.get("phone")
            conn.execute(
                "UPDATE leads SET email=?,phone=?,stage='extracted',updated_at=datetime('now') WHERE id=?",
                (contacts.get("email"), phone, lead["id"]),
            )
        conn.commit()

    # Stage 4: Score
    to_score = [dict(r) for r in conn.execute(
        "SELECT * FROM leads WHERE stage='extracted'"
    ).fetchall()]
    for lead in tqdm(to_score, desc="Scoring"):
        lead["red_flags"] = json.loads(lead.get("red_flags") or "[]")
        r = score_lead(lead)
        conn.execute(
            "UPDATE leads SET lead_score=?,lead_tier=?,stage='scored',updated_at=datetime('now') WHERE id=?",
            (r["lead_score"], r["lead_tier"], lead["id"]),
        )
        c[r["lead_tier"]] = c.get(r["lead_tier"], 0) + 1
    conn.commit()

    # Stage 5: Generate emails
    to_email = [dict(r) for r in conn.execute(
        "SELECT * FROM leads WHERE stage='scored' AND lead_tier IN ('hot','warm')"
    ).fetchall()]
    for lead in tqdm(to_email, desc="Generating emails"):
        emails = generate_emails(lead, conn)
        if emails:
            conn.execute(
                "UPDATE leads SET email_subject=?,email_body_a=?,email_body_b=?,"
                "stage='email_ready',updated_at=datetime('now') WHERE id=?",
                (emails["subject"], emails["body_a"], emails["body_b"], lead["id"]),
            )
        else:
            conn.execute(
                "UPDATE leads SET stage='email_ready',updated_at=datetime('now') WHERE id=?",
                (lead["id"],),
            )
    conn.commit()

    log.info(
        f"Done | New:{c['new']} Hot:{c['hot']} Warm:{c['warm']} "
        f"Low:{c['low']} Uncontactable:{c['uncontactable']} Skipped:{c['skipped']}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    run(dry_run=parser.parse_args().dry_run)
