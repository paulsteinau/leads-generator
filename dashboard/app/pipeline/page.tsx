"use client";
import { useEffect, useRef, useState } from "react";
import DashboardShell from "../components/DashboardShell";
import { getPipelineStatus, startPipeline, stopPipeline, getLogs } from "@/lib/api";

export default function PipelinePage() {
  const [running, setRunning] = useState(false);
  const [pid, setPid] = useState<number | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  const refresh = async () => {
    try {
      const [s, l] = await Promise.all([
        getPipelineStatus(),
        getLogs(120),
      ]);
      setRunning(s.running);
      setPid(s.pid);
      setLogs(l.lines);
      setTimeout(() => logRef.current?.scrollTo({ top: 99999, behavior: "smooth" }), 50);
    } catch {}
  };

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 3000);
    return () => clearInterval(id);
  }, []);

  const run = async (dry: boolean, skipScrape = false) => {
    setError(null);
    const r = await startPipeline(dry, undefined, skipScrape);
    if (r.ok) {
      setRunning(true);
      setPid(r.pid ?? null);
      refresh();
    } else {
      setError(r.error ?? "Fehler beim Starten");
    }
  };

  const stop = async () => {
    await stopPipeline();
    setRunning(false);
    refresh();
  };

  return (
    <DashboardShell>
      <div className="px-6 pt-6 pb-6">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-[18px] font-bold text-gray-900 tracking-tight">Pipeline</h1>
          <p className="text-sm text-gray-400 mt-0.5">Scraping, Analyse und E-Mail-Generierung steuern</p>
        </div>

        {/* Status + Controls */}
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5 mb-4">
          <div className="flex items-center gap-4">
            {/* Status indicator */}
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${running ? "bg-green-50" : "bg-gray-50"}`}>
              {running ? (
                <span className="w-3 h-3 bg-green-500 rounded-full animate-pulse" />
              ) : (
                <span className="w-3 h-3 bg-gray-300 rounded-full" />
              )}
            </div>
            <div>
              <p className="font-semibold text-gray-900">
                {running ? "Pipeline läuft" : "Pipeline gestoppt"}
              </p>
              <p className="text-xs text-gray-400">
                {running ? `PID ${pid}` : "Bereit zum Starten"}
              </p>
            </div>

            <div className="ml-auto flex items-center gap-2">
              {!running && (
                <>
                  <button
                    onClick={() => run(true)}
                    className="px-4 py-2 text-sm font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-xl transition-colors"
                  >
                    Dry Run
                  </button>
                  <button
                    onClick={() => run(false, true)}
                    className="px-4 py-2 text-sm font-semibold text-white bg-emerald-600 hover:bg-emerald-500 rounded-xl transition-colors shadow-sm shadow-emerald-600/20"
                  >
                    Nur Analysieren
                  </button>
                  <button
                    onClick={() => run(false)}
                    className="px-4 py-2 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-500 rounded-xl transition-colors shadow-sm shadow-indigo-600/20"
                  >
                    Pipeline starten
                  </button>
                </>
              )}
              {running && (
                <button
                  onClick={stop}
                  className="px-4 py-2 text-sm font-semibold text-white bg-red-600 hover:bg-red-500 rounded-xl transition-colors"
                >
                  Stoppen
                </button>
              )}
            </div>
          </div>

          {error && (
            <div className="mt-4 bg-red-50 border border-red-100 rounded-xl px-4 py-3">
              <p className="text-red-600 text-sm">{error}</p>
            </div>
          )}
        </div>

        {/* Log viewer */}
        <div className="bg-[#0D0F18] rounded-2xl border border-white/[0.04] overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3 border-b border-white/[0.06]">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 bg-green-500 rounded-full" />
              <p className="text-white/60 text-[12px] font-medium">pipeline.log</p>
            </div>
            <button
              onClick={refresh}
              className="text-white/30 hover:text-white/60 text-[11px] transition-colors"
            >
              Aktualisieren
            </button>
          </div>
          <div
            ref={logRef}
            className="h-[calc(100vh-340px)] min-h-[300px] overflow-y-auto px-5 py-4 font-mono text-[12px] text-green-400/90 leading-relaxed"
          >
            {logs.length === 0 ? (
              <span className="text-white/20">Noch kein Log vorhanden. Starte die Pipeline.</span>
            ) : (
              logs.map((line, i) => (
                <div
                  key={i}
                  className={`${
                    line.includes("ERROR") || line.includes("error")
                      ? "text-red-400"
                      : line.includes("WARNING") || line.includes("warning")
                      ? "text-yellow-400"
                      : line.includes("INFO")
                      ? "text-green-400/90"
                      : "text-white/30"
                  }`}
                >
                  {line}
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </DashboardShell>
  );
}
