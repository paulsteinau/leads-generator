"use client";
import { useEffect, useState } from "react";

interface Costs {
  today_usd: number;
  month_usd: number;
  total_usd: number;
  total_emails: number;
  today_tokens_in: number;
  today_tokens_out: number;
}

export default function CostTracker() {
  const [costs, setCosts] = useState<Costs | null>(null);
  const [open, setOpen] = useState(false);

  const refresh = async () => {
    try {
      const r = await fetch("http://localhost:8000/costs", { cache: "no-store" });
      setCosts(await r.json());
    } catch {}
  };

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 10000);
    return () => clearInterval(id);
  }, []);

  if (!costs) return null;

  const fmt = (n: number) =>
    n < 0.01 ? `< $0.01` : `$${n.toFixed(3)}`;

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-800 px-2 py-1 rounded hover:bg-gray-100 transition-colors"
      >
        <span>💰</span>
        <span className="font-mono">{fmt(costs.month_usd)}</span>
        <span className="text-gray-300">/Monat</span>
        <span className="text-gray-300 ml-1">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="absolute right-0 top-8 bg-white border rounded-xl shadow-lg p-4 z-50 w-64 text-sm">
          <h3 className="font-semibold text-gray-800 mb-3 text-xs uppercase tracking-wide">
            API Kosten (Claude Haiku)
          </h3>
          <div className="space-y-2">
            <div className="flex justify-between">
              <span className="text-gray-500">Heute</span>
              <span className="font-mono font-semibold text-gray-900">{fmt(costs.today_usd)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Dieser Monat</span>
              <span className="font-mono font-semibold text-blue-600">{fmt(costs.month_usd)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Gesamt</span>
              <span className="font-mono font-semibold text-gray-900">{fmt(costs.total_usd)}</span>
            </div>
            <div className="border-t pt-2 mt-2 space-y-1.5">
              <div className="flex justify-between text-xs text-gray-400">
                <span>Emails generiert</span>
                <span className="font-mono">{costs.total_emails}</span>
              </div>
              <div className="flex justify-between text-xs text-gray-400">
                <span>Tokens heute (In/Out)</span>
                <span className="font-mono">
                  {costs.today_tokens_in.toLocaleString()} / {costs.today_tokens_out.toLocaleString()}
                </span>
              </div>
            </div>
            <div className="border-t pt-2 mt-1 text-xs text-gray-300">
              $0.80/MTok Input · $4.00/MTok Output
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
