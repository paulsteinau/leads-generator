import { getLead } from "@/lib/api";
import EmailPanel from "./EmailPanel";
import Link from "next/link";

function Bar({ label, v }: { label: string; v: number | null }) {
  if (v === null)
    return <div className="text-gray-300 text-xs mb-2">{label}: —</div>;
  const col = v >= 70 ? "bg-green-500" : v >= 50 ? "bg-yellow-400" : "bg-red-500";
  return (
    <div className="mb-3">
      <div className="flex justify-between text-xs mb-1">
        <span className="text-gray-600">{label}</span>
        <span className={`font-mono font-semibold ${v >= 70 ? "text-green-600" : v >= 50 ? "text-yellow-600" : "text-red-600"}`}>
          {v}/100
        </span>
      </div>
      <div className="h-2 bg-gray-100 rounded-full">
        <div className={`h-2 rounded-full ${col}`} style={{ width: `${v}%` }} />
      </div>
    </div>
  );
}

function Check({ ok, label }: { ok: boolean | null; label: string }) {
  if (ok === null) return null;
  return (
    <div className={`flex items-center gap-1.5 text-xs ${ok ? "text-green-600" : "text-red-500"}`}>
      <span>{ok ? "✓" : "✗"}</span>
      <span>{label}</span>
    </div>
  );
}

export default async function LeadPage({ params }: { params: { id: string } }) {
  const lead = await getLead(Number(params.id));

  const tierColor =
    lead.lead_tier === "hot" ? "bg-red-100 text-red-700" :
    lead.lead_tier === "warm" ? "bg-orange-100 text-orange-700" :
    "bg-gray-100 text-gray-500";

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b px-6 py-3 flex items-center gap-3">
        <Link href="/" className="text-blue-600 text-sm hover:underline">
          ← Alle Leads
        </Link>
        <span className="text-gray-300">|</span>
        <span className="font-semibold text-gray-900">{lead.name}</span>
        {lead.lead_tier && (
          <span className={`px-2 py-0.5 rounded text-xs font-bold ${tierColor}`}>
            {lead.lead_tier.toUpperCase()} · {lead.lead_score} Punkte
          </span>
        )}
        <span className="text-xs text-gray-400 ml-auto">Stage: {lead.stage}</span>
      </div>

      <div className="p-6 grid grid-cols-3 gap-5">
        {/* Col 1: Firmendaten */}
        <div className="space-y-4">
          <div className="bg-white rounded-xl p-5 border">
            <h2 className="font-semibold text-xs text-gray-400 uppercase tracking-wide mb-3">Firma</h2>
            <p className="font-bold text-lg text-gray-900 mb-0.5">{lead.name}</p>
            <p className="text-gray-500 text-sm">{lead.category} · {lead.district}</p>
            {lead.address && <p className="text-xs text-gray-400 mt-2">{lead.address}</p>}
            {lead.website && (
              <a href={lead.website} target="_blank" className="text-blue-600 text-sm block mt-2 hover:underline truncate">
                {lead.website}
              </a>
            )}
          </div>

          <div className="bg-white rounded-xl p-5 border">
            <h2 className="font-semibold text-xs text-gray-400 uppercase tracking-wide mb-3">Kontakt</h2>
            {lead.phone ? (
              <a href={`tel:${lead.phone}`} className="flex items-center gap-2 text-sm text-gray-800 hover:text-blue-600 mb-2">
                <span>📞</span> {lead.phone}
              </a>
            ) : <p className="text-xs text-gray-300 mb-2">Keine Telefonnummer</p>}
            {lead.email ? (
              <p className="flex items-center gap-2 text-sm text-gray-800 break-all">
                <span>✉</span> {lead.email}
              </p>
            ) : <p className="text-xs text-gray-300">Keine E-Mail</p>}
          </div>

          <div className="bg-white rounded-xl p-5 border">
            <h2 className="font-semibold text-xs text-gray-400 uppercase tracking-wide mb-3">Google</h2>
            <p className="text-2xl font-bold text-gray-900">{lead.google_rating ?? "—"}<span className="text-sm text-yellow-500"> ★</span></p>
            <p className="text-sm text-gray-500">{lead.google_reviews ?? 0} Bewertungen</p>
            <div className="flex gap-2 mt-3 flex-wrap">
              {lead.has_instagram && <span className="text-xs bg-pink-50 text-pink-600 px-2 py-0.5 rounded">Instagram</span>}
              {lead.has_facebook && <span className="text-xs bg-blue-50 text-blue-600 px-2 py-0.5 rounded">Facebook</span>}
              {lead.has_linkedin && <span className="text-xs bg-sky-50 text-sky-600 px-2 py-0.5 rounded">LinkedIn</span>}
              {!lead.has_instagram && !lead.has_facebook && !lead.has_linkedin && (
                <span className="text-xs text-gray-300">Keine Social Media gefunden</span>
              )}
            </div>
          </div>
        </div>

        {/* Col 2: Analyse */}
        <div className="space-y-4">
          <div className="bg-white rounded-xl p-5 border">
            <h2 className="font-semibold text-xs text-gray-400 uppercase tracking-wide mb-4">Website-Analyse</h2>
            <Bar label="Mobile PageSpeed" v={lead.pagespeed_mobile} />
            <Bar label="Desktop PageSpeed" v={lead.pagespeed_desktop} />
            <Bar label="SEO Score" v={lead.seo_score} />
            <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 mt-4 pt-4 border-t">
              <Check ok={lead.has_ssl} label="SSL" />
              <Check ok={lead.is_mobile_ready} label="Mobile-ready" />
              <Check ok={lead.has_cta} label="Call-to-Action" />
              <Check ok={lead.has_booking} label="Online-Buchung" />
            </div>
            {lead.cms_detected && (
              <p className="text-xs text-gray-400 mt-3">CMS: <span className="font-medium text-gray-600">{lead.cms_detected}</span></p>
            )}
          </div>

          {lead.red_flags.length > 0 && (
            <div className="bg-white rounded-xl p-5 border">
              <h2 className="font-semibold text-xs text-gray-400 uppercase tracking-wide mb-3">Schwachstellen</h2>
              <div className="flex flex-wrap gap-1.5">
                {lead.red_flags.map((f) => (
                  <span key={f} className="px-2 py-1 bg-red-50 text-red-600 text-xs rounded-lg border border-red-100">
                    {f}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Col 3: Email + CRM */}
        <EmailPanel lead={lead} />
      </div>
    </div>
  );
}
