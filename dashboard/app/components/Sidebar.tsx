"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

interface Stats {
  hot: number;
  warm: number;
  low: number;
  contacted: number;
  replied: number;
  new_today: number;
}

interface CostStats {
  today_usd: number;
  month_usd: number;
  demos_total: number;
  cost_per_demo_avg: number;
}

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";
const _secret = process.env.NEXT_PUBLIC_API_SECRET ?? "";
const authHeaders = () => ({ Authorization: `Bearer ${_secret}` });

export default function Sidebar() {
  const pathname = usePathname();
  const [stats, setStats] = useState<Stats | null>(null);
  const [costs, setCosts] = useState<CostStats | null>(null);
  const [running, setRunning] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const [s, p, c] = await Promise.all([
          fetch(`${API}/stats`, { cache: "no-store", headers: authHeaders() }).then((r) => r.json()),
          fetch(`${API}/pipeline/status`, { cache: "no-store", headers: authHeaders() }).then((r) => r.json()),
          fetch(`${API}/costs`, { cache: "no-store", headers: authHeaders() }).then((r) => r.json()),
        ]);
        setStats(s);
        setRunning(p.running ?? false);
        setCosts(c);
      } catch {}
    };
    fetchStats();
    const id = setInterval(fetchStats, 15000);
    return () => clearInterval(id);
  }, []);

  const handleLogout = async () => {
    setLoggingOut(true);
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } finally {
      window.location.href = "/login";
    }
  };

  const isLeads = pathname === "/" || pathname.startsWith("/leads");
  const isPipeline = pathname === "/pipeline";

  return (
    <aside className="w-[210px] flex-shrink-0 bg-[#0D0F18] flex flex-col h-full border-r border-white/[0.04]">
      {/* Brand */}
      <div className="px-5 py-5 border-b border-white/[0.06]">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-indigo-600 flex items-center justify-center shadow-md shadow-indigo-600/30 flex-shrink-0">
            <span className="text-white font-bold text-xs">B</span>
          </div>
          <div>
            <p className="text-white font-semibold text-[13px] leading-none tracking-tight">BerlinLeads</p>
            <p className="text-white/25 text-[10px] mt-0.5">Lead System</p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-white/20 px-3 mb-3">
          Navigation
        </p>

        <Link
          href="/"
          className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all duration-150 group ${
            isLeads
              ? "bg-white/10 text-white font-medium"
              : "text-white/45 hover:text-white/80 hover:bg-white/[0.05]"
          }`}
        >
          <svg className="w-3.5 h-3.5 flex-shrink-0" viewBox="0 0 16 16" fill="none">
            <path d="M2 4h12M2 8h8M2 12h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
          Leads
          {stats && stats.hot > 0 && (
            <span className="ml-auto inline-flex items-center justify-center w-4 h-4 text-[9px] font-bold bg-red-500 text-white rounded-full flex-shrink-0">
              {stats.hot}
            </span>
          )}
        </Link>

        <Link
          href="/pipeline"
          className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all duration-150 ${
            isPipeline
              ? "bg-white/10 text-white font-medium"
              : "text-white/45 hover:text-white/80 hover:bg-white/[0.05]"
          }`}
        >
          <svg className="w-3.5 h-3.5 flex-shrink-0" viewBox="0 0 16 16" fill="none">
            <path d="M8 2v4l2.5 2.5M14 8A6 6 0 112 8a6 6 0 0112 0z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
          Pipeline
          <span className={`ml-auto w-1.5 h-1.5 rounded-full flex-shrink-0 ${running ? "bg-green-400 animate-pulse" : "bg-white/15"}`} />
        </Link>
      </nav>

      {/* Stats summary */}
      {stats && (
        <div className="mx-3 mb-3 bg-white/[0.04] rounded-xl p-3 border border-white/[0.06]">
          <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-white/20 mb-2.5">Übersicht</p>
          <div className="grid grid-cols-2 gap-y-2 gap-x-3">
            <div>
              <p className="text-[11px] text-white/35">Hot</p>
              <p className="text-sm font-bold text-red-400 tabular">{stats.hot}</p>
            </div>
            <div>
              <p className="text-[11px] text-white/35">Warm</p>
              <p className="text-sm font-bold text-orange-400 tabular">{stats.warm}</p>
            </div>
            <div>
              <p className="text-[11px] text-white/35">Heute</p>
              <p className="text-sm font-bold text-indigo-400 tabular">{stats.new_today}</p>
            </div>
            <div>
              <p className="text-[11px] text-white/35">Contacted</p>
              <p className="text-sm font-bold text-green-400 tabular">{stats.contacted}</p>
            </div>
          </div>

          {costs && (
            <>
              <div className="my-2.5 border-t border-white/[0.06]" />
              <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-white/20 mb-2">API Kosten</p>
              <div className="grid grid-cols-2 gap-y-2 gap-x-3">
                <div>
                  <p className="text-[11px] text-white/35">Heute</p>
                  <p className="text-sm font-bold text-yellow-400 tabular">${costs.today_usd.toFixed(3)}</p>
                </div>
                <div>
                  <p className="text-[11px] text-white/35">Monat</p>
                  <p className="text-sm font-bold text-yellow-300 tabular">${costs.month_usd.toFixed(2)}</p>
                </div>
                <div>
                  <p className="text-[11px] text-white/35">Demos</p>
                  <p className="text-sm font-bold text-white/60 tabular">{costs.demos_total}</p>
                </div>
                <div>
                  <p className="text-[11px] text-white/35">Ø/Demo</p>
                  <p className="text-sm font-bold text-white/60 tabular">
                    {costs.cost_per_demo_avg > 0 ? `$${costs.cost_per_demo_avg.toFixed(3)}` : "—"}
                  </p>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* Logout */}
      <div className="px-3 pb-4 border-t border-white/[0.06] pt-3">
        <button
          onClick={handleLogout}
          disabled={loggingOut}
          className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-white/35 hover:text-white/60 hover:bg-white/[0.05] transition-all duration-150 text-sm disabled:opacity-50"
        >
          <svg className="w-3.5 h-3.5 flex-shrink-0" viewBox="0 0 16 16" fill="none">
            <path d="M6 14H3a1 1 0 01-1-1V3a1 1 0 011-1h3M10 11l3-3-3-3M13 8H6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          {loggingOut ? "Abmelden..." : "Abmelden"}
        </button>
      </div>
    </aside>
  );
}
