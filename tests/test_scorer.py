from pipeline.scorer.engine import score_lead


def base(**kw):
    d = {
        "category": "Friseur", "google_reviews": 20, "red_flags": [],
        "is_mobile_ready": True, "pagespeed_mobile": 70, "seo_score": 60,
        "has_cta": True, "has_booking": True, "has_ssl": True,
        "cms_detected": None, "has_instagram": False, "has_facebook": False,
        "email": "x@y.de", "phone": "030123",
    }
    d.update(kw)
    return d


def test_high_roi_adds_3():
    assert score_lead(base(category="Zahnarzt"))["lead_score"] == \
           score_lead(base())["lead_score"] + 3


def test_no_website_adds_4():
    assert score_lead(base(red_flags=["no_website"]))["lead_score"] == \
           score_lead(base())["lead_score"] + 4


def test_many_reviews_adds_3():
    assert score_lead(base(google_reviews=60))["lead_score"] == \
           score_lead(base())["lead_score"] + 3


def test_hot_tier_at_12():
    r = score_lead(base(category="Zahnarzt", google_reviews=60,
                        red_flags=["no_website"], is_mobile_ready=False))
    assert r["lead_tier"] == "hot" and r["lead_score"] >= 12


def test_uncontactable_no_email_no_phone():
    assert score_lead(base(email=None, phone=None))["lead_tier"] == "uncontactable"


def test_fast_mobile_penalty():
    lead_normal = base(category="Zahnarzt", google_reviews=60)
    lead_fast = base(category="Zahnarzt", google_reviews=60, pagespeed_mobile=85)
    assert score_lead(lead_fast)["lead_score"] == score_lead(lead_normal)["lead_score"] - 3


def test_score_never_negative():
    assert score_lead(base(pagespeed_mobile=95, cms_detected="custom",
                           google_reviews=2))["lead_score"] >= 0


def test_low_tier_default():
    assert score_lead(base())["lead_tier"] == "low"
