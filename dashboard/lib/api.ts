const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const SECRET = process.env.NEXT_PUBLIC_API_SECRET ?? "";

const authHeaders = (): HeadersInit =>
  SECRET ? { Authorization: `Bearer ${SECRET}` } : {};

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
  demo_url: string | null;
  demo_screenshots: string | null;
  audit_score: number | null;
  qualification: string | null;
  industry_tag: string | null;
  description: string | null;
  email_subject: string | null;
  email_subjects: string | null;
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

export interface CostStats {
  today_usd: number;
  month_usd: number;
  total_usd: number;
  demos_total: number;
  cost_per_demo_avg: number;
  by_model: { model: string; total_usd: number; calls: number }[];
  today_tokens_in: number;
  today_tokens_out: number;
}

export interface LogResponse {
  lines: string[];
}

export const getStats = (): Promise<Stats> =>
  fetch(`${API}/stats`, { cache: "no-store", headers: authHeaders() }).then((r) => r.json());

export const getCosts = (): Promise<CostStats> =>
  fetch(`${API}/costs`, { cache: "no-store", headers: authHeaders() }).then((r) => r.json());

export const getLeads = (p?: Record<string, string>): Promise<LeadSummary[]> =>
  fetch(`${API}/leads${p ? "?" + new URLSearchParams(p) : ""}`, { cache: "no-store", headers: authHeaders() }).then((r) =>
    r.json()
  );

export const getLead = (id: number): Promise<LeadDetail> =>
  fetch(`${API}/leads/${id}`, { cache: "no-store", headers: authHeaders() }).then((r) => r.json());

export const approveEmail = (id: number, variant: "a" | "b") =>
  fetch(`${API}/leads/${id}/approve-email`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ variant }),
  });

export const updateStatus = (id: number, status: string) =>
  fetch(`${API}/leads/${id}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ status }),
  });

export const updateEmail = (id: number, email: string) =>
  fetch(`${API}/leads/${id}/email`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ email }),
  });

export const getPipelineStatus = (): Promise<PipelineStatus> =>
  fetch(`${API}/pipeline/status`, { cache: "no-store", headers: authHeaders() }).then((r) => r.json());

export const startPipeline = (dryRun = false): Promise<{ ok: boolean; pid?: number; error?: string }> =>
  fetch(`${API}/pipeline/start?dry_run=${dryRun}`, { method: "POST", headers: authHeaders() }).then((r) => r.json());

export const stopPipeline = (): Promise<{ ok: boolean }> =>
  fetch(`${API}/pipeline/stop`, { method: "POST", headers: authHeaders() }).then((r) => r.json());

export const getLogs = (lines = 100): Promise<LogResponse> =>
  fetch(`${API}/pipeline/logs?lines=${lines}`, { cache: "no-store", headers: authHeaders() }).then((r) => r.json());

export const getPendingReview = (): Promise<{ count: number }> =>
  fetch(`${API}/leads/pending-review`, { cache: "no-store", headers: authHeaders() }).then((r) => r.json());

export async function generateDemo(leadId: number): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch(`${API}/leads/${leadId}/generate-demo`, { method: "POST", headers: authHeaders() });
  return res.json();
}

export async function getDemoStatus(leadId: number): Promise<{
  stage: string; sub_stage: string | null; demo_url: string | null; has_screenshots: boolean; ready: boolean; failed: boolean;
}> {
  const res = await fetch(`${API}/leads/${leadId}/demo-status`, { headers: authHeaders() });
  return res.json();
}

export async function approveLead(leadId: number): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch(`${API}/leads/${leadId}/approve`, { method: "POST", headers: authHeaders() });
  return res.json();
}

export async function rejectLead(leadId: number): Promise<{ ok: boolean }> {
  const res = await fetch(`${API}/leads/${leadId}/reject`, { method: "POST", headers: authHeaders() });
  return res.json();
}

export async function createManualLead(data: {
  name: string; website?: string; category?: string; district?: string;
  phone?: string; email?: string; lead_tier?: string; notes?: string;
}): Promise<{ ok: boolean; id?: number; error?: string }> {
  const res = await fetch(`${API}/leads/manual`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(data),
  });
  if (res.status === 409) return { ok: false, error: "Lead existiert bereits" };
  return res.json();
}

export async function editDemo(leadId: number, description: string): Promise<{ ok: boolean }> {
  const res = await fetch(`${API}/leads/${leadId}/edit-demo`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ description }),
  });
  return res.json();
}

export async function resetDemo(leadId: number): Promise<{ ok: boolean }> {
  const res = await fetch(`${API}/leads/${leadId}/reset-demo`, { method: "POST", headers: authHeaders() });
  return res.json();
}
