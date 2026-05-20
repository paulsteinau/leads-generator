"use client";
import { useEffect, useRef, useState } from "react";
import { getPipelineStatus, startPipeline, stopPipeline, getLogs } from "@/lib/api";

export default function PipelinePanel() {
  const [running, setRunning] = useState(false);
  const [pid, setPid] = useState<number | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  const refresh = async () => {
    const s = await getPipelineStatus();
    setRunning(s.running);
    setPid(s.pid);
    if (open) {
      const l = await getLogs(80);
      setLogs(l.lines);
      setTimeout(() => logRef.current?.scrollTo(0, 9999), 50);
    }
  };

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 4000);
    return () => clearInterval(id);
  }, [open]);

  const run = async (dry: boolean) => {
    const r = await startPipeline(dry);
    if (r.ok) { setRunning(true); setPid(r.pid ?? null); setOpen(true); }
    else alert(r.error ?? "Fehler");
  };

  const stop = async () => {
    await stopPipeline();
    setRunning(false);
  };

  return (
    <div className="bg-white border-b">
      <div className="flex items-center gap-3 px-4 py-3">
        <span className="text-sm font-semibold text-gray-700">Pipeline</span>
        <span className={`w-2 h-2 rounded-full ${running ? "bg-green-500 animate-pulse" : "bg-gray-300"}`} />
        <span className="text-xs text-gray-400">{running ? `PID ${pid}` : "Gestoppt"}</span>
        <div className="flex gap-2 ml-auto">
          <button
            onClick={() => run(false)}
            disabled={running}
            className="px-3 py-1.5 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-40"
          >
            Run Pipeline
          </button>
          <button
            onClick={() => run(true)}
            disabled={running}
            className="px-3 py-1.5 text-xs bg-gray-600 text-white rounded hover:bg-gray-700 disabled:opacity-40"
          >
            Dry Run
          </button>
          {running && (
            <button
              onClick={stop}
              className="px-3 py-1.5 text-xs bg-red-600 text-white rounded hover:bg-red-700"
            >
              Stop
            </button>
          )}
          <button
            onClick={() => { setOpen(!open); if (!open) refresh(); }}
            className="px-3 py-1.5 text-xs border rounded hover:bg-gray-50"
          >
            {open ? "Log ausblenden" : "Log anzeigen"}
          </button>
        </div>
      </div>
      {open && (
        <div
          ref={logRef}
          className="h-48 overflow-y-auto bg-gray-950 px-4 py-3 font-mono text-xs text-green-400 leading-relaxed"
        >
          {logs.length === 0 ? (
            <span className="text-gray-500">Noch kein Log vorhanden.</span>
          ) : (
            logs.map((l, i) => <div key={i}>{l}</div>)
          )}
        </div>
      )}
    </div>
  );
}
