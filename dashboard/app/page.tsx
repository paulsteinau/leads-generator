import { getStats, getLeads } from "@/lib/api";
import PipelinePanel from "../components/PipelinePanel";
import CostTracker from "../components/CostTracker";
import Link from "next/link";

const TIER: Record<string, string> = {
  hot: "bg-red-100 text-red-700",
  warm: "bg-orange-100 text-orange-700",
  low: "bg-gray-100 text-gray-500",
  uncontactable: "bg-purple-100 text-purple-500",
};

const STATUS: Record<string, string> = {
  new: "text-gray-400",
  contacted: "text-blue-500",
  replied: "text-green-600 font-semibold",
  closed: "text-gray-400 line-through",
  ignored: "text-gray-300",
};

export default async function Home({
  searchParams,
}: {
  searchParams: Record<string, string>;
}) {
  const [stats, leads] = await Promise.all([getStats(), getLeads(searchParams)]);
  const activeTier = searchParams.tier;

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b px-4 py-3 flex items-center gap-2">
        <span className="font-bold text-gray-900">Berlin Lead-Gen</span>
        <span className="text-gray-300 mx-1">|</span>
        <span className="text-sm text-gray-500">internes Tool</span>
        <div className="ml-auto">
          <CostTracker />
        </div>
      </div>

      {/* Pipeline Control */}
      <PipelinePanel />

      {/* Stats Bar */}
      <div className="flex gap-6 px-4 py-3 bg-white border-b text-sm">
        <span>Heute: <b className="text-blue-600">{stats.new_today}</b></span>
        <span>Hot: <b className="text-red-600">{stats.hot}</b></span>
        <span>Warm: <b className="text-orange-500">{stats.warm}</b></span>
        <span>Low: <b className="text-gray-400">{stats.low}</b></span>
        <span className="ml-auto">Contacted: <b>{stats.contacted}</b></span>
        <span>Replied: <b className="text-green-600">{stats.replied}</b></span>
        <a
          href="/api/leads/export"
          className="text-xs text-blue-600 hover:underline"
        >
          CSV Export
        </a>
      </div>

      {/* Filter Bar */}
      <div className="flex gap-2 px-4 py-2 bg-white border-b text-sm flex-wrap">
        <span className="text-gray-400 text-xs self-center">Filter:</span>
        {["hot", "warm", "low"].map((t) => (
          <a
            key={t}
            href={`?tier=${t}`}
            className={`px-3 py-1 border rounded text-xs capitalize ${
              activeTier === t ? "bg-gray-800 text-white border-gray-800" : "hover:bg-gray-50"
            }`}
          >
            {t}
          </a>
        ))}
        <a
          href="/"
          className={`px-3 py-1 border rounded text-xs ${
            !activeTier ? "bg-gray-800 text-white border-gray-800" : "hover:bg-gray-50"
          }`}
        >
          Alle
        </a>
        <span className="ml-auto text-xs text-gray-400">{leads.length} Leads</span>
      </div>

      {/* Lead Table */}
      {leads.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-gray-400">
          <p className="text-lg font-medium mb-2">Noch keine Leads</p>
          <p className="text-sm">Starte die Pipeline oben um Leads zu generieren.</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm bg-white">
            <thead className="border-b text-xs text-gray-500 uppercase bg-gray-50 sticky top-0">
              <tr>
                {["Firma", "Branche", "Bezirk", "Score", "Tier", "Stage", "Email", "Status", ""].map(
                  (h) => (
                    <th key={h} className="px-4 py-3 text-left font-medium">
                      {h}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody>
              {leads.map((l) => (
                <tr key={l.id} className="border-b hover:bg-blue-50 transition-colors">
                  <td className="px-4 py-3 font-medium text-gray-900">{l.name ?? "—"}</td>
                  <td className="px-4 py-3 text-gray-500">{l.category}</td>
                  <td className="px-4 py-3 text-gray-500">{l.district}</td>
                  <td className="px-4 py-3 font-mono text-sm">
                    {l.lead_score !== null ? (
                      <span className={l.lead_score >= 12 ? "text-red-600 font-bold" : l.lead_score >= 7 ? "text-orange-500 font-semibold" : "text-gray-400"}>
                        {l.lead_score}
                      </span>
                    ) : "—"}
                  </td>
                  <td className="px-4 py-3">
                    {l.lead_tier && (
                      <span className={`px-2 py-0.5 rounded text-xs font-semibold ${TIER[l.lead_tier] ?? ""}`}>
                        {l.lead_tier.toUpperCase()}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-400 text-xs">{l.stage}</td>
                  <td className="px-4 py-3 text-center">
                    {l.has_email ? (
                      <span className="text-green-500 font-bold">✓</span>
                    ) : (
                      <span className="text-gray-300">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {l.follow_up_due ? (
                      <span className="text-orange-500 font-semibold text-xs bg-orange-50 px-2 py-0.5 rounded">
                        Follow-up!
                      </span>
                    ) : (
                      <span className={`text-xs ${STATUS[l.status] ?? ""}`}>{l.status}</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <Link
                      href={`/leads/${l.id}`}
                      className="text-blue-600 hover:underline text-xs"
                    >
                      Detail →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
