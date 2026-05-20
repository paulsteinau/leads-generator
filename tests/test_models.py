from api.models import LeadSummary, StatsResponse


def test_lead_summary():
    lead = LeadSummary(
        id=1, name="Test", category="Zahnarzt", district="Mitte",
        lead_score=14, lead_tier="hot", stage="scored", status="new",
        has_email=True, follow_up_due=False, created_at="2026-05-19",
    )
    assert lead.lead_tier == "hot"
    assert lead.has_email is True


def test_stats():
    s = StatsResponse(hot=5, warm=12, low=30, new_today=10, contacted=3, replied=1)
    assert s.hot == 5
    assert s.replied == 1
