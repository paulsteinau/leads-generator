HIGH_ROI = {"Zahnarzt", "Anwalt", "Immobilienmakler"}


def score_lead(lead: dict) -> dict:
    flags = lead.get("red_flags") or []
    score = 0

    if "no_website" in flags:
        score += 4
    if lead.get("category") in HIGH_ROI:
        score += 3
    if (lead.get("google_reviews") or 0) > 50:
        score += 3
    if not lead.get("is_mobile_ready") or "no_mobile" in flags:
        score += 3

    mobile = lead.get("pagespeed_mobile")
    if mobile is not None and mobile < 50:
        score += 2

    seo = lead.get("seo_score")
    if seo is not None and seo < 40:
        score += 2

    has_socials = lead.get("has_instagram") or lead.get("has_facebook")
    if has_socials and (not lead.get("is_mobile_ready") or "no_mobile" in flags):
        score += 2

    if not lead.get("has_cta") or "no_cta" in flags:
        score += 2

    cms = (lead.get("cms_detected") or "").lower()
    if any(c in cms for c in ["wix", "jimdo", "squarespace"]):
        score += 2
    if not lead.get("has_ssl") or "no_ssl" in flags:
        score += 1
    if not lead.get("has_booking") or "no_booking" in flags:
        score += 1

    # Penalties
    if mobile is not None and mobile > 80:
        score -= 3
    if (lead.get("google_reviews") or 0) < 5:
        score -= 1

    score = max(0, score)

    if not lead.get("email") and not lead.get("phone"):
        return {"lead_score": score, "lead_tier": "uncontactable"}

    tier = "hot" if score >= 12 else "warm" if score >= 7 else "low"
    return {"lead_score": score, "lead_tier": tier}
