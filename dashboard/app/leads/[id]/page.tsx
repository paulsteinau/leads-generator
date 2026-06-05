import { getLead } from "@/lib/api";
import EmailPanel from "./EmailPanel";
import ReviewPanel from "./ReviewPanel";
import ScreenshotTabs from "./ScreenshotTabs";
import Link from "next/link";
import GenerateDemoButton from "./GenerateDemoButton";
import DashboardShell from "../../components/DashboardShell";

const TIER_COLORS: Record<string, { bg: string; text: string; ring: string }> = {
  hot:  { bg: "bg-red-50",    text: "text-red-700",    ring: "ring-red-200"    },
  warm: { bg: "bg-orange-50", text: "text-orange-700", ring: "ring-orange-200" },
  low:  { bg: "bg-gray-100",  text: "text-gray-500",   ring: "ring-gray-200"   },
};

function ScoreBar({ label, v }: { label: string; v: number | null }) {
  if (v === null)
    return <div className="text-gray-300 text-xs mb-3">{label}: —</div>;
  const col = v >= 70 ? "bg-green-500" : v >= 50 ? "bg-amber-400" : "bg-red-400";
  const txt = v >= 70 ? "text-green-600" : v >= 50 ? "text-amber-600" : "text-red-600";
  return (
    <div className="mb-3">
      <div className="flex justify-between text-xs mb-1.5">
        <span className="text-gray-500">{label}</span>
        <span className={`font-mono font-bold ${txt}`}>{v}/100</span>
      </div>
      <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-1.5 rounded-full transition-all ${col}`} style={{ width: `${v}%` }} />
      </div>
    </div>
  );
}

function Check({ ok, label }: { ok: boolean | null; label: string }) {
  if (ok === null) return null;
  return (
    <div className={`flex items-center gap-1.5 text-xs ${ok ? "text-green-600" : "text-red-500"}`}>
      <span className={`w-4 h-4 rounded-full flex items-center justify-center flex-shrink-0 ${ok ? "bg-green-100" : "bg-red-50"}`}>
        {ok ? (
          <svg className="w-2.5 h-2.5" viewBox="0 0 10 10" fill="none"><path d="M2 5l2 2 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
        ) : (
          <svg className="w-2.5 h-2.5" viewBox="0 0 10 10" fill="none"><path d="M3 3l4 4M7 3l-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
        )}
      </span>
      <span>{label}</span>
    </div>
  );
}

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-gray-300 mb-4">{title}</p>
      {children}
    </div>
  );
}

export default async function LeadPage({ params }: { params: { id: string } }) {
  const lead = await getLead(Number(params.id));

  const tier = lead.lead_tier ?? "low";
  const tc = TIER_COLORS[tier] ?? TIER_COLORS.low;

  let demoScreenshots: string[] = [];
  if (lead.demo_screenshots) {
    try { demoScreenshots = JSON.parse(lead.demo_screenshots) as string[]; } catch {}
  }

  const SCREENSHOT_LABELS = ["Desktop Home", "Desktop Full", "Mobile Home", "Mobile Full"];

  return (
    <DashboardShell>
      {/* Breadcrumb / header */}
      <div className="bg-white border-b border-gray-100 px-6 py-4 flex items-center gap-3">
        <Link
          href="/"
          className="flex items-center gap-1.5 text-gray-400 hover:text-gray-700 transition-colors text-sm"
        >
          <svg className="w-4 h-4" viewBox="0 0 16 16" fill="none">
            <path d="M10 12L6 8l4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          Leads
        </Link>
        <svg className="w-3 h-3 text-gray-200" viewBox="0 0 12 12" fill="none"><path d="M4 2l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
        <span className="font-semibold text-gray-900 text-sm">{lead.name}</span>

        <div className="flex items-center gap-2 ml-2">
          {lead.lead_tier && (
            <span className={`inline-flex items-center px-2.5 py-1 rounded-lg text-xs font-bold uppercase tracking-wide ${tc.bg} ${tc.text} ring-1 ${tc.ring}`}>
              {lead.lead_tier}
            </span>
          )}
          {lead.lead_score !== null && (
            <span className="text-xs text-gray-400 font-mono">{lead.lead_score} Punkte</span>
          )}
        </div>

        <span className="ml-auto text-[11px] text-gray-300 bg-gray-50 px-2.5 py-1 rounded-lg">
          {lead.stage}
        </span>
      </div>

      {/* 3-column grid */}
      <div className="p-6 grid grid-cols-3 gap-4">
        {/* ── Col 1: Business data ── */}
        <div className="space-y-3">
          <SectionCard title="Firma">
            <p className="font-bold text-[17px] text-gray-900 leading-tight mb-1">{lead.name}</p>
            <p className="text-gray-500 text-sm">{[lead.category, lead.district].filter(Boolean).join(" · ")}</p>
            {lead.address && (
              <p className="text-xs text-gray-400 mt-2 leading-relaxed">{lead.address}</p>
            )}
            {lead.website && (
              <a
                href={lead.website}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 text-indigo-600 text-sm mt-3 hover:underline truncate"
              >
                <svg className="w-3 h-3 flex-shrink-0" viewBox="0 0 12 12" fill="none"><path d="M7 1h4v4M11 1L5 7M4 3H2a1 1 0 00-1 1v6a1 1 0 001 1h6a1 1 0 001-1V8" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                <span className="truncate">{lead.website.replace(/^https?:\/\//, "")}</span>
              </a>
            )}
          </SectionCard>

          <SectionCard title="Kontakt">
            {lead.phone ? (
              <a href={`tel:${lead.phone}`} className="flex items-center gap-2 text-sm text-gray-700 hover:text-indigo-600 transition-colors mb-2">
                <span className="w-6 h-6 bg-gray-50 rounded-lg flex items-center justify-center flex-shrink-0 text-gray-400">
                  <svg className="w-3 h-3" viewBox="0 0 12 12" fill="none"><path d="M1 2.5A1.5 1.5 0 012.5 1h.879a.5.5 0 01.47.327l.954 2.547a.5.5 0 01-.113.542L3.5 5.125a7.127 7.127 0 003.375 3.375l.71-1.19a.5.5 0 01.542-.113l2.547.954A.5.5 0 0111 8.62V9.5A1.5 1.5 0 019.5 11C4.253 11 1 7.247 1 2.5z" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>
                </span>
                {lead.phone}
              </a>
            ) : <p className="text-xs text-gray-200 mb-2">Keine Telefonnummer</p>}
            {lead.email ? (
              <div className="flex items-center gap-2 text-sm text-gray-700">
                <span className="w-6 h-6 bg-gray-50 rounded-lg flex items-center justify-center flex-shrink-0 text-gray-400">
                  <svg className="w-3 h-3" viewBox="0 0 12 12" fill="none"><path d="M1 3a1 1 0 011-1h8a1 1 0 011 1v6a1 1 0 01-1 1H2a1 1 0 01-1-1V3zm9 0L6 6.5 2 3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>
                </span>
                <span className="truncate text-xs">{lead.email}</span>
              </div>
            ) : <p className="text-xs text-gray-200">Keine E-Mail</p>}
          </SectionCard>

          <SectionCard title="Google & Social">
            <div className="flex items-end gap-2 mb-3">
              <p className="text-3xl font-bold text-gray-900 leading-none">{lead.google_rating ?? "—"}</p>
              <span className="text-yellow-400 text-lg mb-0.5">★</span>
              <span className="text-xs text-gray-400 mb-1">{lead.google_reviews ?? 0} Bewertungen</span>
            </div>
            <div className="flex gap-1.5 flex-wrap">
              {lead.has_instagram && (
                <span className="text-[11px] bg-pink-50 text-pink-600 px-2 py-0.5 rounded-md font-medium">Instagram</span>
              )}
              {lead.has_facebook && (
                <span className="text-[11px] bg-blue-50 text-blue-600 px-2 py-0.5 rounded-md font-medium">Facebook</span>
              )}
              {lead.has_linkedin && (
                <span className="text-[11px] bg-sky-50 text-sky-600 px-2 py-0.5 rounded-md font-medium">LinkedIn</span>
              )}
              {!lead.has_instagram && !lead.has_facebook && !lead.has_linkedin && (
                <span className="text-xs text-gray-300">Kein Social Media gefunden</span>
              )}
            </div>
          </SectionCard>

          {(lead.audit_score !== null || lead.qualification || lead.industry_tag) && (
            <SectionCard title="KI-Audit">
              <div className="flex flex-wrap gap-2 mb-3">
                {lead.audit_score !== null && (
                  <span className={`px-2.5 py-1 rounded-lg text-xs font-bold ${
                    lead.audit_score < 40 ? "bg-red-100 text-red-700" :
                    lead.audit_score <= 65 ? "bg-amber-100 text-amber-700" :
                    "bg-green-100 text-green-700"
                  }`}>
                    Score {lead.audit_score}
                  </span>
                )}
                {lead.qualification && (
                  <span className={`px-2.5 py-1 rounded-lg text-xs font-medium ${
                    lead.qualification === "bad_website" ? "bg-red-50 text-red-600" :
                    lead.qualification === "mediocre" ? "bg-amber-50 text-amber-700" :
                    "bg-green-50 text-green-700"
                  }`}>
                    {lead.qualification === "bad_website" ? "Schlechte Website" :
                     lead.qualification === "mediocre" ? "Mittelmäßig" : "Gute Website"}
                  </span>
                )}
                {lead.industry_tag && (
                  <span className="px-2.5 py-1 rounded-lg text-xs bg-gray-100 text-gray-500">
                    {lead.industry_tag}
                  </span>
                )}
              </div>
              {lead.description && (
                <p className="text-xs text-gray-500 leading-relaxed">
                  {lead.description.length > 150 ? lead.description.slice(0, 150) + "…" : lead.description}
                </p>
              )}
            </SectionCard>
          )}
        </div>

        {/* ── Col 2: Analysis ── */}
        <div className="space-y-3">
          <SectionCard title="Website-Analyse">
            <ScoreBar label="Mobile PageSpeed" v={lead.pagespeed_mobile} />
            <ScoreBar label="Desktop PageSpeed" v={lead.pagespeed_desktop} />
            <ScoreBar label="SEO Score" v={lead.seo_score} />
            <div className="grid grid-cols-2 gap-x-3 gap-y-2 mt-4 pt-4 border-t border-gray-50">
              <Check ok={lead.has_ssl} label="SSL" />
              <Check ok={lead.is_mobile_ready} label="Mobile-ready" />
              <Check ok={lead.has_cta} label="Call-to-Action" />
              <Check ok={lead.has_booking} label="Online-Buchung" />
            </div>
            {lead.cms_detected && (
              <p className="text-xs text-gray-400 mt-3">
                CMS: <span className="font-semibold text-gray-600">{lead.cms_detected}</span>
              </p>
            )}
          </SectionCard>

          {lead.red_flags.length > 0 && (
            <SectionCard title="Schwachstellen">
              <div className="flex flex-wrap gap-1.5">
                {lead.red_flags.map((f) => (
                  <span key={f} className="px-2.5 py-1 bg-red-50 text-red-600 text-[11px] font-medium rounded-lg border border-red-100">
                    {f}
                  </span>
                ))}
              </div>
            </SectionCard>
          )}

          {lead.demo_url && (
            <SectionCard title="Demo-Vorschau">
              <div className="relative">
                <iframe
                  src={lead.demo_url}
                  className="w-full h-80 rounded-xl border border-gray-100"
                  title="Demo-Vorschau"
                />
                <a
                  href={lead.demo_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-3 flex items-center justify-center gap-1.5 text-xs font-medium text-indigo-600 hover:underline"
                >
                  In neuem Tab öffnen
                  <svg className="w-3 h-3" viewBox="0 0 12 12" fill="none"><path d="M7 1h4v4M11 1L5 7M4 3H2a1 1 0 00-1 1v6a1 1 0 001 1h6a1 1 0 001-1V8" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                </a>
              </div>
            </SectionCard>
          )}

          {demoScreenshots.length > 0 && (
            <SectionCard title="Screenshots">
              <ScreenshotTabs shots={demoScreenshots} labels={SCREENSHOT_LABELS} />
            </SectionCard>
          )}
        </div>

        {/* ── Col 3: Actions ── */}
        <div className="space-y-3">
          <GenerateDemoButton
            leadId={lead.id}
            initialStage={lead.stage ?? ""}
            initialDemoUrl={lead.demo_url ?? null}
          />
          {lead.stage === "ready_for_review" && <ReviewPanel lead={lead} />}
          <EmailPanel lead={lead} />
        </div>
      </div>
    </DashboardShell>
  );
}
