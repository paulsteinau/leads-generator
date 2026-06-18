"use client";
import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const SECRET = process.env.NEXT_PUBLIC_API_SECRET ?? "";
const authHeaders = (): HeadersInit => SECRET ? { Authorization: `Bearer ${SECRET}` } : {};

const STAGE_LABEL: Record<string, string> = {
  scraped:          "Scraped",
  analyzed:         "Analysiert",
  extracted:        "Extrahiert",
  scored:           "Bewertet",
  email_generated:  "Email bereit",
  ready_for_review: "Review",
  approved:         "Freigegeben",
  sent:             "Versendet",
  generating_demo:  "Demo läuft",
  demo_failed:      "Demo fehlgeschlagen",
};

const STATUS_LABEL: Record<string, string> = {
  new:           "Neu",
  contacted:     "Kontaktiert",
  replied:       "Geantwortet",
  closed:        "Abgeschlossen",
  ignored:       "Ignoriert",
  uncontactable: "Nicht erreichbar",
};

interface Options {
  categories: string[];
  districts: string[];
  stages: string[];
  statuses: string[];
  dates: string[];
}

function fmtDate(d: string) {
  const [y, m, day] = d.split("-");
  return `${day}.${m}.${y}`;
}

export default function LeadsFilters({ totalLeads }: { totalLeads: number }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [opts, setOpts] = useState<Options>({ categories: [], districts: [], stages: [], statuses: [], dates: [] });

  useEffect(() => {
    fetch(`${API}/leads/filter-options`, { cache: "no-store", headers: authHeaders() })
      .then((r) => r.json())
      .then(setOpts)
      .catch(() => {});
  }, []);

  const update = (key: string, val: string) => {
    const p = new URLSearchParams(params.toString());
    if (val) p.set(key, val);
    else p.delete(key);
    router.push(`${pathname}?${p.toString()}`);
  };

  const FILTER_KEYS = ["tier", "stage", "status", "category", "district", "date"];
  const hasFilters = FILTER_KEYS.some((k) => params.get(k));
  const activeTier = params.get("tier");

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm px-4 py-3 flex items-center gap-2 flex-wrap">
      <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-gray-300 mr-1">Filter:</span>

      {/* Tier buttons */}
      {(["all", "hot", "warm", "low"] as const).map((val) => {
        const isActive = val === "all" ? !activeTier : activeTier === val;
        return (
          <button
            key={val}
            onClick={() => val === "all" ? update("tier", "") : update("tier", val)}
            className={`h-7 px-3 rounded-lg text-xs font-medium transition-all ${
              isActive ? "bg-gray-900 text-white" : "text-gray-500 hover:text-gray-800 hover:bg-gray-50"
            }`}
          >
            {val === "all" ? "Alle" : val.charAt(0).toUpperCase() + val.slice(1)}
          </button>
        );
      })}

      <div className="w-px h-4 bg-gray-100" />

      {/* Review quick-filter */}
      <button
        onClick={() => update("stage", params.get("stage") === "ready_for_review" ? "" : "ready_for_review")}
        className={`h-7 px-3 rounded-lg text-xs font-medium transition-all ${
          params.get("stage") === "ready_for_review"
            ? "bg-orange-500 text-white"
            : "text-gray-500 hover:text-gray-800 hover:bg-gray-50"
        }`}
      >
        Review ausstehend
      </button>

      <div className="w-px h-4 bg-gray-100" />

      {/* Dropdown filters */}
      {[
        {
          name: "date",
          placeholder: "Datum",
          options: opts.dates,
          labelMap: Object.fromEntries(opts.dates.map((d) => [d, fmtDate(d)])),
        },
        { name: "category", placeholder: "Kategorie", options: opts.categories },
        { name: "district",  placeholder: "Bezirk",    options: opts.districts  },
        { name: "stage",     placeholder: "Stage",     options: opts.stages,    labelMap: STAGE_LABEL  },
        { name: "status",    placeholder: "Status",    options: opts.statuses,  labelMap: STATUS_LABEL },
      ].map(({ name, placeholder, options, labelMap }) => (
        <select
          key={name}
          value={params.get(name) ?? ""}
          onChange={(e) => update(name, e.target.value)}
          className={`h-7 px-2 pr-6 text-[12px] border rounded-lg appearance-none focus:outline-none focus:border-indigo-400 transition-colors cursor-pointer ${
            params.get(name)
              ? "border-indigo-300 bg-indigo-50 text-indigo-700 font-medium"
              : "border-gray-200 bg-white text-gray-600 hover:border-gray-300"
          }`}
          style={{ backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%239ca3af' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round' fill='none'/%3E%3C/svg%3E\")", backgroundRepeat: "no-repeat", backgroundPosition: "right 8px center" }}
        >
          <option value="">{placeholder}</option>
          {options.map((o) => (
            <option key={o} value={o}>{labelMap ? (labelMap[o] ?? o) : o}</option>
          ))}
        </select>
      ))}

      {hasFilters && (
        <button
          onClick={() => router.push(pathname)}
          className="h-7 px-2.5 rounded-lg text-[11px] font-medium text-red-400 hover:bg-red-50 hover:text-red-600 transition-colors"
        >
          Zurücksetzen
        </button>
      )}

      <span className="ml-auto text-xs text-gray-400 tabular">{totalLeads} Leads</span>
    </div>
  );
}
