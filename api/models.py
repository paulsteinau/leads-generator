from pydantic import BaseModel
from typing import Optional


class LeadSummary(BaseModel):
    id: int
    name: Optional[str] = None
    category: Optional[str] = None
    district: Optional[str] = None
    lead_score: Optional[int] = None
    lead_tier: Optional[str] = None
    stage: str
    status: str
    has_email: bool
    follow_up_due: bool
    created_at: str


class LeadDetail(BaseModel):
    id: int
    name: Optional[str] = None
    category: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    google_rating: Optional[float] = None
    google_reviews: Optional[int] = None
    has_instagram: bool = False
    has_facebook: bool = False
    has_linkedin: bool = False
    pagespeed_mobile: Optional[int] = None
    pagespeed_desktop: Optional[int] = None
    has_ssl: Optional[bool] = None
    cms_detected: Optional[str] = None
    has_cta: Optional[bool] = None
    has_booking: Optional[bool] = None
    is_mobile_ready: Optional[bool] = None
    seo_score: Optional[int] = None
    red_flags: list[str] = []
    lead_score: Optional[int] = None
    lead_tier: Optional[str] = None
    stage: str
    email_subject: Optional[str] = None
    email_body_a: Optional[str] = None
    email_body_b: Optional[str] = None
    email_approved: bool = False
    email_variant: Optional[str] = None
    email_subjects: Optional[str] = None
    status: str
    notes: Optional[str] = None
    description: Optional[str] = None
    industry_tag: Optional[str] = None
    audit_score: Optional[int] = None
    qualification: Optional[str] = None
    demo_url: Optional[str] = None
    demo_generated_at: Optional[str] = None
    demo_screenshots: Optional[str] = None
    created_at: str
    updated_at: str


class StatsResponse(BaseModel):
    hot: int
    warm: int
    low: int
    new_today: int
    contacted: int
    replied: int


class ManualLeadRequest(BaseModel):
    name: str
    website: Optional[str] = None
    category: Optional[str] = None
    district: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    lead_tier: str = "warm"
    notes: Optional[str] = None


class ApproveEmailRequest(BaseModel):
    variant: str  # "a" or "b"


class UpdateStatusRequest(BaseModel):
    status: str


class UpdateEmailRequest(BaseModel):
    email: Optional[str] = None


class PendingReviewLead(BaseModel):
    id: int
    name: Optional[str] = None
    demo_url: Optional[str] = None
    created_at: str


class RegenerateRequest(BaseModel):
    instructions: Optional[str] = None


class EditDemoRequest(BaseModel):
    description: str


class ResendWebhookPayload(BaseModel):
    type: str
    data: Optional[dict] = None


class UnsubscribeRequest(BaseModel):
    email: str
    domain: Optional[str] = None
