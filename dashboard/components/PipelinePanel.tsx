"use client";
import { useEffect, useRef, useState } from "react";
import { getPipelineStatus, startPipeline, stopPipeline, getLogs } from "../app/lib/api";

interface Progress {
  current: number;
  total: number;
  label: string;
  stage: string;
  etaSec: number | null;
}

function parseProgress(lines: string[]): Progress | null {
  let total = 0;
  let current = 0;
  let label = "";
  let stage = "Scraping";
  let startTime: number | null = null;
  const progressTimes: number[] = [];

  for (const line of lines) {
    const stageMatch = line.match(/Stage 1: (\d+) queries/);
    if (stageMatch) total = parseInt(stageMatch[1]);

    const progMatch = line.match(/PROGRESS (\d+)\/(\d+) (.+)/);
    if (progMatch) {
      current = parseInt(progMatch[1]);
      total = parseInt(progMatch[2]);
      label = progMatch[3];
      stage = "Scraping";
      const tsMatch = line.match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})/);
      if (tsMatch) {
        const t = new Date(tsMatch[1]).getTime();
        if (!startTime) startTime = t;
        progressTimes.push(t);
      }
    }

    if (line.includes("Stage 2:")) stage = "Analyzing";
    if (line.includes("Extracting")) stage = "Extracting";
    if (line.includes("Scoring")) stage = "Scoring";
    if (line.includes("Generating emails")) stage = "Emails";
    if (line.includes("Done |")) { stage = "Done"; current = total; }
  }

  if (total === 0) return null;

  let etaSec: number | null = null;
  if (progressTimes.length >= 2 && current < total) {
    const elapsed = progressTimes[progressTimes.length - 1] - progressTimes[0];
    const perItem = elapsed / (progressTimes.length - 1);
    etaSec = Math.round((perItem * (total - current)) / 1000);
  }

  return { current, total, label, stage, etaSec };
}

function fmtEta(sec: number): string {
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return s > 0 ? `${m}m ${s}s` : `${m}m`;
}

export default function PipelinePanel() {
  const [running, setRunning] = useState(false);
  const [pid, setPid] = useState<number | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const [progress, setProgress] = useState<Progress | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  const refresh = async () => {
    try {
      const s = await getPipelineStatus();
      setRunning(s.running);
      setPid(s.pid);
      const l = await getLogs(200);
      setLogs(l.lines);
      setProgress(parseProgress(l.lines));
      if (open) setTimeout(() => logRef.current?.scrollTo(0, 9999), 50);
    } catch {}
  };

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 4000);
    return () => clearInterval(id);
  }, [open]);

  const run = async (dry: boolean) => {
    try {
      const r = await startPipeline(dry);
      if (r.ok) { setRunning(true); setPid(r.pid ?? null); setOpen(true); }
      else alert(r.error ?? "Fehler");
    } catch {
      alert("API nicht erreichbar. Ist start_api.bat aktiv?");
    }
  };

  const stop = async () => {
    try { await stopPipeline(); } catch {}
    setRunning(false);
  };

  const pct = progress && progress.total > 0
    ? Math.round((progress.current / progress.total) * 100)
    : 0;

  return (
    <div className="bg-white border-b">
      <div className="flex items-center gap-3 px-4 py-3">
        <span className="text-sm font-semibold text-gray-700">Pipeline</span>
        <span className={`w-2 h-2 rounded-full ${running ? "bg-green-500 animate-pulse" : "bg-gray-300"}`} />
        <span className="text-xs text-gray-400">{running ? `PID ${pid}` : "Gestoppt"}</span>
        <div className="flex gap-2 ml-auto">
          <button onClick={() => run(false)} disabled={running}
            className="px-3 py-1.5 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-40">
            Run Pipeline
          </button>
          <button onClick={() => run(true)} disabled={running}
            className="px-3 py-1.5 text-xs bg-gray-600 text-white rounded hover:bg-gray-700 disabled:opacity-40">
            Dry Run
          </button>
          {running && (
            <button onClick={stop}
              className="px-3 py-1.5 text-xs bg-red-600 text-white rounded hover:bg-red-700">
              Stop
            </button>
          )}
          <button onClick={() => { setOpen(!open); if (!open) refresh(); }}
            className="px-3 py-1.5 text-xs border rounded hover:bg-gray-50">
            {open ? "Log ausblenden" : "Log anzeigen"}
          </button>
        </div>
      </div>

      {/* Progress bar */}
      {running && progress && (
        <div className="px-4 pb-3">
          <div className="flex items-center justify-between text-xs text-gray-500 mb-1">
            <span>
              <span className="font-medium text-gray-700">{progress.stage}</span>
              {progress.label && (
                <span className="ml-2 text-gray-400 truncate max-w-xs inline-block align-bottom">{progress.label}</span>
              )}
            </span>
            <span className="font-mono tabular-nums">
              {progress.current}/{progress.total}
              {progress.etaSec !== null && (
                <span className="ml-2 text-gray-400">~ {fmtEta(progress.etaSec)} verbleibend</span>
              )}
            </span>
          </div>
          <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 rounded-full transition-all duration-700"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      )}

      {open && (
        <div ref={logRef}
          className="h-48 overflow-y-auto bg-gray-950 px-4 py-3 font-mono text-xs text-green-400 leading-relaxed">
          {logs.length === 0
            ? <span className="text-gray-500">Noch kein Log vorhanden.</span>
            : logs.map((l, i) => (
              <div key={i} className={
                l.includes("ERROR") ? "text-red-400" :
                l.includes("PROGRESS") ? "text-blue-400" :
                l.includes("Done |") ? "text-yellow-400" :
                "text-green-400"
              }>{l}</div>
            ))}
        </div>
      )}
    </div>
  );
}
