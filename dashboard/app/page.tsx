import { getStats, getLeads, getCosts } from "@/lib/api";
import Link from "next/link";
import DashboardShell from "./components/DashboardShell";
import AddLeadButton from "./components/AddLeadButton";

const TIER_STYLES: Record<string, { badge: string; initials: string }> = {
  hot:  { badge: "bg-red-50 text-red-700 ring-1 ring-red-200",    initials: "bg-red-500 text-white" },
  warm: { badge: "bg-orange-50 text-orange-700 ring-1 ring-orange-200", initials: "bg-orange-500 text-white" },
  low:  { badge: "bg-gray-100 text-gray-500 ring-1 ring-gray-200", initials: "bg-gray-400 text-white" },
};

const STATUS_STYLES: Record<string, string> = {
  new:           "text-gray-400",
  contacted:     "text-indigo-600 font-medium",
  replied:       "text-green-600 font-semibold",
  closed:        "text-gray-300 line-through",
  ignored:       "text-gray-300",
  uncontactable: "text-gray-300",
};

const STAGE_LABEL: Record<string, string> = {
  scraped:          "Scraped",
  analyzed:         "Analysiert",
  scored:           "Bewertet",
  email_generated:  "Email bereit",
  ready_for_review: "Review",
  approved:         "Freigegeben",
  sent:             "Versendet",
  generating_demo:  "Demo läuft...",
  demo_failed:      "Demo fehlgeschlagen",
};

function getInitials(name: string | null): string {
  if (!name) return "?";
  const words = name.trim().split(/\s+/);
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

export default async function Home({
  searchParams,
}: {
  searchParams: Record<string, string>;
}) {
  const [stats, leads, costs] = await Promise.all([getStats(), getLeads(searchParams), getCosts()]);
  const activeTier = searchParams.tier;
  const activeStatus = searchParams.status;

  const totalLeads = leads.length;
  const withEmail = leads.filter((l) => l.has_email).length;

  return (
    <DashboardShell>
      {/* Page header */}
      <div className="px-6 pt-6 pb-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-[18px] font-bold text-gray-900 tracking-tight">Leads</h1>
            <p className="text-sm text-gray-400 mt-0.5">
              {totalLeads} Leads · {withEmail} mit E-Mail
            </p>
          </div>
          <div className="flex items-center gap-2">
            <AddLeadButton />
          </div>
        </div>
      </div>

      {/* Stats cards */}
      <div className="px-6 pb-4 space-y-3">
        <div className="grid grid-cols-4 gap-3">
          {[
            { label: "Hot",       value: stats.hot,       color: "text-red-600",    bg: "bg-red-50",     ring: "ring-red-100",    dot: "bg-red-500"    },
            { label: "Warm",      value: stats.warm,      color: "text-orange-600", bg: "bg-orange-50",  ring: "ring-orange-100", dot: "bg-orange-500" },
            { label: "Neu heute", value: stats.new_today, color: "text-indigo-600", bg: "bg-indigo-50",  ring: "ring-indigo-100", dot: "bg-indigo-500" },
            { label: "Contacted", value: stats.contacted, color: "text-green-600",  bg: "bg-green-50",   ring: "ring-green-100",  dot: "bg-green-500"  },
          ].map((s) => (
            <div
              key={s.label}
              className="bg-white rounded-2xl border border-gray-100 shadow-sm px-5 py-4 flex items-center justify-between"
            >
              <div>
                <p className="text-xs text-gray-400 font-medium mb-1">{s.label}</p>
                <p className={`text-2xl font-bold tabular ${s.color}`}>{s.value}</p>
              </div>
              <div className={`w-8 h-8 ${s.bg} ring-1 ${s.ring} rounded-xl flex items-center justify-center`}>
                <div className={`w-2 h-2 ${s.dot} rounded-full`} />
              </div>
            </div>
          ))}
        </div>

        {/* Cost row */}
        <div className="grid grid-cols-4 gap-3">
          {[
            { label: "API heute",   value: `$${costs.today_usd.toFixed(3)}`,          color: "text-amber-600", bg: "bg-amber-50",  ring: "ring-amber-100",  dot: "bg-amber-400" },
            { label: "API Monat",   value: `$${costs.month_usd.toFixed(2)}`,           color: "text-amber-700", bg: "bg-amber-50",  ring: "ring-amber-100",  dot: "bg-amber-500" },
            { label: "Demos gen.",  value: String(costs.demos_total),                  color: "text-violet-600", bg: "bg-violet-50", ring: "ring-violet-100", dot: "bg-violet-400" },
            { label: "Ø Kosten/Demo", value: costs.cost_per_demo_avg > 0 ? `$${costs.cost_per_demo_avg.toFixed(3)}` : "—", color: "text-gray-600", bg: "bg-gray-50", ring: "ring-gray-100", dot: "bg-gray-300" },
          ].map((s) => (
            <div
              key={s.label}
              className="bg-white rounded-2xl border border-gray-100 shadow-sm px-5 py-4 flex items-center justify-between"
            >
              <div>
                <p className="text-xs text-gray-400 font-medium mb-1">{s.label}</p>
                <p className={`text-2xl font-bold tabular ${s.color}`}>{s.value}</p>
              </div>
              <div className={`w-8 h-8 ${s.bg} ring-1 ${s.ring} rounded-xl flex items-center justify-center`}>
                <div className={`w-2 h-2 ${s.dot} rounded-full`} />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Filters */}
      <div className="px-6 pb-3">
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm px-4 py-3 flex items-center gap-2 flex-wrap">
          <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-gray-300 mr-1">Filter:</span>
          {[
            { key: "tier", val: undefined, label: "Alle" },
            { key: "tier", val: "hot",  label: "Hot" },
            { key: "tier", val: "warm", label: "Warm" },
            { key: "tier", val: "low",  label: "Low" },
          ].map((f) => {
            const isActive = f.val ? activeTier === f.val : !activeTier && !activeStatus;
            const href = f.val ? `?tier=${f.val}` : "/";
            return (
              <a
                key={`${f.key}-${f.val ?? "all"}`}
                href={href}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
                  isActive
                    ? "bg-gray-900 text-white"
                    : "text-gray-500 hover:text-gray-800 hover:bg-gray-50"
                }`}
              >
                {f.label}
              </a>
            );
          })}
          <div className="w-px h-4 bg-gray-100 mx-1" />
          <a
            href="?status=pending_review"
            className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
              activeStatus === "pending_review"
                ? "bg-orange-500 text-white"
                : "text-gray-500 hover:text-gray-800 hover:bg-gray-50"
            }`}
          >
            Review ausstehend
          </a>
          <span className="ml-auto text-xs text-gray-400 tabular">{totalLeads} Leads</span>
        </div>
      </div>

      {/* Lead table */}
      <div className="px-6 pb-6">
        {leads.length === 0 ? (
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm flex flex-col items-center justify-center py-20">
            <div className="w-12 h-12 bg-gray-100 rounded-2xl flex items-center justify-center mb-4">
              <svg className="w-6 h-6 text-gray-300" viewBox="0 0 24 24" fill="none">
                <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 012-2h2a2 2 0 012 2M9 5h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            <p className="text-gray-500 font-medium mb-1">Noch keine Leads</p>
            <p className="text-gray-400 text-sm">Starte die Pipeline unter &quot;Pipeline&quot;.</p>
          </div>
        ) : (
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-50">
                  {["Firma", "Kategorie", "Bezirk", "Score", "Tier", "Stage", "Email", "Status", ""].map((h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.06em] text-gray-400"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {leads.map((l, idx) => {
                  const tier = l.lead_tier ?? "low";
                  const tStyle = TIER_STYLES[tier] ?? TIER_STYLES.low;
                  return (
                    <tr
                      key={l.id}
                      className={`border-b border-gray-50 last:border-0 hover:bg-indigo-50/30 transition-colors duration-100 ${idx % 2 === 0 ? "" : "bg-gray-50/40"}`}
                    >
                      {/* Firma */}
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <div className={`w-8 h-8 rounded-lg ${tStyle.initials} flex items-center justify-center text-[11px] font-bold flex-shrink-0`}>
                            {getInitials(l.name)}
                          </div>
                          <span className="font-semibold text-gray-900 text-[13px]">{l.name ?? "—"}</span>
                        </div>
                      </td>
                      {/* Kategorie */}
                      <td className="px-4 py-3 text-gray-500 text-[13px]">{l.category ?? "—"}</td>
                      {/* Bezirk */}
                      <td className="px-4 py-3 text-gray-400 text-[13px]">{l.district ?? "—"}</td>
                      {/* Score */}
                      <td className="px-4 py-3">
                        {l.lead_score !== null ? (
                          <span className={`tabular font-bold text-[13px] ${
                            l.lead_score >= 12 ? "text-red-600" : l.lead_score >= 7 ? "text-orange-500" : "text-gray-400"
                          }`}>
                            {l.lead_score}
                          </span>
                        ) : (
                          <span className="text-gray-200">—</span>
                        )}
                      </td>
                      {/* Tier */}
                      <td className="px-4 py-3">
                        {l.lead_tier && (
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-bold uppercase tracking-wider ${tStyle.badge}`}>
                            {l.lead_tier}
                          </span>
                        )}
                      </td>
                      {/* Stage */}
                      <td className="px-4 py-3">
                        <span className="text-[12px] text-gray-400">
                          {STAGE_LABEL[l.stage] ?? l.stage}
                        </span>
                      </td>
                      {/* Email */}
                      <td className="px-4 py-3 text-center">
                        {l.has_email ? (
                          <span className="inline-flex w-5 h-5 items-center justify-center bg-green-100 rounded-full">
                            <svg className="w-3 h-3 text-green-600" viewBox="0 0 12 12" fill="none">
                              <path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                            </svg>
                          </span>
                        ) : (
                          <span className="text-gray-200 text-xs">—</span>
                        )}
                      </td>
                      {/* Status */}
                      <td className="px-4 py-3">
                        {l.follow_up_due ? (
                          <span className="text-orange-600 font-semibold text-[12px] bg-orange-50 px-2 py-0.5 rounded-md">
                            Follow-up
                          </span>
                        ) : (
                          <span className={`text-[12px] capitalize ${STATUS_STYLES[l.status] ?? "text-gray-400"}`}>
                            {l.status}
                          </span>
                        )}
                      </td>
                      {/* Action */}
                      <td className="px-4 py-3 text-right">
                        <Link
                          href={`/leads/${l.id}`}
                          className="inline-flex items-center gap-1 text-[12px] font-medium text-indigo-600 hover:text-indigo-700 hover:bg-indigo-50 px-2.5 py-1.5 rounded-lg transition-all duration-100"
                        >
                          Öffnen
                          <svg className="w-3 h-3" viewBox="0 0 12 12" fill="none">
                            <path d="M2 6h8M6 2l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                          </svg>
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </DashboardShell>
  );
}
