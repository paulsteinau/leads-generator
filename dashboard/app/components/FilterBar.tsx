"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

interface Props {
  categories: string[];
  districts: string[];
  totalLeads: number;
}

const DATE_OPTIONS = [
  { label: "Alle", value: "" },
  { label: "Heute", value: "today" },
  { label: "7 Tage", value: "7d" },
  { label: "30 Tage", value: "30d" },
];

function isoDate(daysAgo: number) {
  const d = new Date();
  d.setDate(d.getDate() - daysAgo);
  return d.toISOString().slice(0, 10);
}

function dateParamToValue(param: string | null): string {
  if (!param) return "";
  const today = new Date().toISOString().slice(0, 10);
  const week  = isoDate(7);
  const month = isoDate(30);
  if (param >= today) return "today";
  if (param >= week)  return "7d";
  if (param >= month) return "30d";
  return "";
}

export default function FilterBar({ categories, districts, totalLeads }: Props) {
  const router = useRouter();
  const sp = useSearchParams();

  const get = (k: string) => sp.get(k) ?? "";

  const update = useCallback((key: string, value: string) => {
    const params = new URLSearchParams(sp.toString());
    if (value) params.set(key, value);
    else params.delete(key);
    router.push(`/?${params.toString()}`);
  }, [sp, router]);

  const setDate = (val: string) => {
    const params = new URLSearchParams(sp.toString());
    if (!val) {
      params.delete("date_from");
    } else if (val === "today") {
      params.set("date_from", new Date().toISOString().slice(0, 10));
    } else if (val === "7d") {
      params.set("date_from", isoDate(7));
    } else if (val === "30d") {
      params.set("date_from", isoDate(30));
    }
    router.push(`/?${params.toString()}`);
  };

  const activeDateVal = dateParamToValue(get("date_from"));
  const activeTier = get("tier");
  const activeStage = get("stage");
  const activeCategory = get("category");
  const activeDistrict = get("district");

  const hasFilters = activeTier || activeStage || activeCategory || activeDistrict || get("date_from");

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm px-4 py-3 space-y-2.5">
      <div className="flex items-center gap-2 flex-wrap">
        {/* Tier pills */}
        <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-gray-300 mr-1">Tier:</span>
        {[
          { val: "", label: "Alle" },
          { val: "hot",  label: "Hot" },
          { val: "warm", label: "Warm" },
          { val: "low",  label: "Low" },
        ].map((f) => (
          <button
            key={f.val || "all-tier"}
            onClick={() => update("tier", f.val)}
            className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
              activeTier === f.val
                ? "bg-gray-900 text-white"
                : "text-gray-500 hover:text-gray-800 hover:bg-gray-50"
            }`}
          >
            {f.label}
          </button>
        ))}

        <div className="w-px h-4 bg-gray-100 mx-1" />

        {/* Stage pill */}
        <button
          onClick={() => update("stage", activeStage === "ready_for_review" ? "" : "ready_for_review")}
          className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
            activeStage === "ready_for_review"
              ? "bg-orange-500 text-white"
              : "text-gray-500 hover:text-gray-800 hover:bg-gray-50"
          }`}
        >
          Review ausstehend
        </button>

        {hasFilters && (
          <button
            onClick={() => router.push("/")}
            className="ml-auto text-[11px] text-gray-400 hover:text-gray-600 transition-colors"
          >
            Filter zurücksetzen
          </button>
        )}
        <span className={`${hasFilters ? "" : "ml-auto"} text-xs text-gray-400 tabular`}>
          {totalLeads} Leads
        </span>
      </div>

      {/* Second row: Date + Category + District */}
      <div className="flex items-center gap-2 flex-wrap pt-1 border-t border-gray-50">
        {/* Date */}
        <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-gray-300 mr-1">Datum:</span>
        {DATE_OPTIONS.map((d) => (
          <button
            key={d.value || "all-date"}
            onClick={() => setDate(d.value)}
            className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
              activeDateVal === d.value
                ? "bg-indigo-600 text-white"
                : "text-gray-500 hover:text-gray-800 hover:bg-gray-50"
            }`}
          >
            {d.label}
          </button>
        ))}

        <div className="w-px h-4 bg-gray-100 mx-1" />

        {/* Category select */}
        <select
          value={activeCategory}
          onChange={(e) => update("category", e.target.value)}
          className="text-xs border border-gray-200 rounded-lg px-2.5 py-1.5 text-gray-600 focus:outline-none focus:ring-2 focus:ring-indigo-300 bg-white"
        >
          <option value="">Alle Kategorien</option>
          {categories.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>

        {/* District select */}
        <select
          value={activeDistrict}
          onChange={(e) => update("district", e.target.value)}
          className="text-xs border border-gray-200 rounded-lg px-2.5 py-1.5 text-gray-600 focus:outline-none focus:ring-2 focus:ring-indigo-300 bg-white"
        >
          <option value="">Alle Bezirke</option>
          {districts.map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
      </div>
    </div>
  );
}
