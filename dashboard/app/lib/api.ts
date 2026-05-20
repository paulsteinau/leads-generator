const API = "http://localhost:8000";

export interface LeadSummary {
  id: number;
  name: string | null;
  category: string | null;
  district: string | null;
  lead_score: number | null;
  lead_tier: string | null;
  stage: string;
  status: string;
  has_email: boolean;
  follow_up_due: boolean;
  created_at: string;
}

export interface LeadDetail {
  id: number;
  name: string | null;
  category: string | null;
  district: string | null;
  address: string | null;
  phone: string | null;
  email: string | null;
  website: string | null;
  google_rating: number | null;
  google_reviews: number | null;
  has_instagram: boolean;
  has_facebook: boolean;
  has_linkedin: boolean;
  pagespeed_mobile: number | null;
  pagespeed_desktop: number | null;
  has_ssl: boolean | null;
  cms_detected: string | null;
  has_cta: boolean | null;
  has_booking: boolean | null;
  is_mobile_ready: boolean | null;
  seo_score: number | null;
  red_flags: string[];
  lead_score: number | null;
  lead_tier: string | null;
  stage: string;
  email_subject: string | null;
  email_body_a: string | null;
  email_body_b: string | null;
  email_approved: boolean;
  email_variant: string | null;
  status: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface Stats {
  hot: number;
  warm: number;
  low: number;
  new_today: number;
  contacted: number;
  replied: number;
}

export interface PipelineStatus {
  running: boolean;
  pid: number | null;
}

export interface LogResponse {
  lines: string[];
}

export const getStats = (): Promise<Stats> =>
  fetch(`${API}/stats`, { cache: "no-store" }).then((r) => r.json());

export const getLeads = (p?: Record<string, string>): Promise<LeadSummary[]> =>
  fetch(`${API}/leads${p ? "?" + new URLSearchParams(p) : ""}`, { cache: "no-store" }).then((r) =>
    r.json()
  );

export const getLead = (id: number): Promise<LeadDetail> =>
  fetch(`${API}/leads/${id}`, { cache: "no-store" }).then((r) => r.json());

export const approveEmail = (id: number, variant: "a" | "b") =>
  fetch(`${API}/leads/${id}/approve-email`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ variant }),
  });

export const updateStatus = (id: number, status: string) =>
  fetch(`${API}/leads/${id}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });

export const getPipelineStatus = (): Promise<PipelineStatus> =>
  fetch(`${API}/pipeline/status`, { cache: "no-store" }).then((r) => r.json());

export const startPipeline = (dryRun = false): Promise<{ ok: boolean; pid?: number; error?: string }> =>
  fetch(`${API}/pipeline/start?dry_run=${dryRun}`, { method: "POST" }).then((r) => r.json());

export const stopPipeline = (): Promise<{ ok: boolean }> =>
  fetch(`${API}/pipeline/stop`, { method: "POST" }).then((r) => r.json());

export const getLogs = (lines = 100): Promise<LogResponse> =>
  fetch(`${API}/pipeline/logs?lines=${lines}`, { cache: "no-store" }).then((r) => r.json());
