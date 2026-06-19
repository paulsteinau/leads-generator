"use client";
import { useState, useEffect, useCallback, useRef } from "react";
import { generateDemo, getDemoStatus, resetDemo } from "@/lib/api";

const SUB_STAGE_CONFIG: Record<string, { pct: number; label: string }> = {
  scraping:          { pct: 5,  label: "Website wird gescraped..." },
  inspiration:       { pct: 12, label: "Design-Inspiration wird geladen..." },
  content_extraction:{ pct: 18, label: "Inhalte werden analysiert..." },
  design_brief:      { pct: 25, label: "Design-Brief wird erstellt..." },
  generating_jsx:    { pct: 30, label: "KI generiert Demo-Code..." },
  jsx_validation:    { pct: 75, label: "Code wird validiert..." },
  npm_install:       { pct: 82, label: "Pakete werden installiert..." },
  npm_build:         { pct: 88, label: "Website wird gebaut..." },
  vercel_deploy:     { pct: 93, label: "Demo wird deployed..." },
};

const JSX_MAX_TOKENS = 32000;

interface Props {
  leadId: number;
  initialStage: string;
  initialDemoUrl: string | null;
}

const DONE_STAGES = new Set(["ready_for_review", "approved", "rejected"]);
const FAILED_STAGES = new Set(["demo_build_failed", "demo_failed"]);

export default function GenerateDemoButton({ leadId, initialStage, initialDemoUrl }: Props) {
  const [stage, setStage] = useState(initialStage);
  const [subStage, setSubStage] = useState<string | null>(null);
  const [demoUrl, setDemoUrl] = useState(initialDemoUrl);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isPolling, setIsPolling] = useState(initialStage === "generating_demo");
  const seenGenerating = useRef(false);
  // Parse token progress from sub_stage like "generating_jsx:14200"
  const isGeneratingJsx = subStage?.startsWith("generating_jsx") ?? false;
  const jsxTokens = (() => {
    if (!subStage?.includes(":")) return null;
    const n = parseInt(subStage.split(":")[1]);
    return isNaN(n) ? null : n;
  })();

  const poll = useCallback(async () => {
    const status = await getDemoStatus(leadId);
    setStage(status.stage);
    setSubStage(status.sub_stage);
    if (status.demo_url) setDemoUrl(status.demo_url);
    return status;
  }, [leadId]);

  useEffect(() => {
    if (!isPolling) return;
    seenGenerating.current = false;

    const interval = setInterval(async () => {
      const status = await poll();

      if (status.stage === "generating_demo") {
        seenGenerating.current = true;
      }

      const isDone = DONE_STAGES.has(status.stage) || !!status.demo_url;
      // only stop on failure after we've seen the new run start (avoids stopping on stale failed state)
      const isFailed = FAILED_STAGES.has(status.stage) && seenGenerating.current;

      if (isDone || isFailed) {
        clearInterval(interval);
        setIsPolling(false);
        if (isDone) {
          window.location.reload();
        }
      }
    }, 4000);

    return () => clearInterval(interval);
  }, [isPolling, poll]);

  const handleGenerate = async () => {
    setLoading(true);
    setError(null);
    const result = await generateDemo(leadId);
    if (result.ok) {
      setStage("generating_demo");
      setIsPolling(true);
    } else {
      setError(result.error || "Fehler beim Starten");
    }
    setLoading(false);
  };

  const handleReset = async () => {
    if (!confirm("Demo löschen und neu generieren?")) return;
    setLoading(true);
    setError(null);
    await resetDemo(leadId);
    setDemoUrl(null);
    setStage("scored");
    setLoading(false);
  };

  if ((demoUrl || DONE_STAGES.has(stage)) && !loading) {
    return (
      <div className="bg-white rounded-xl border p-4 flex items-center justify-between gap-3">
        <p className="text-xs text-gray-400">Demo vorhanden</p>
        <button
          onClick={handleReset}
          disabled={loading}
          className="px-3 py-1.5 text-xs bg-gray-100 hover:bg-red-50 hover:text-red-600 text-gray-500 rounded-lg font-medium transition-colors disabled:opacity-60"
        >
          {loading ? "..." : "Neu generieren"}
        </button>
      </div>
    );
  }

  if (isPolling || stage === "generating_demo") {
    const baseKey = subStage?.split(":")[0] ?? "";
    const cfg = SUB_STAGE_CONFIG[baseKey] ?? null;
    const pct = isGeneratingJsx
      ? (jsxTokens !== null
          ? Math.round(30 + (jsxTokens / JSX_MAX_TOKENS) * 42)
          : 30)
      : (cfg?.pct ?? 2);
    const label = isGeneratingJsx
      ? (jsxTokens !== null
          ? `KI generiert Demo-Code... ${(jsxTokens / 1000).toFixed(1)}k / ~${(JSX_MAX_TOKENS / 1000).toFixed(0)}k Tokens`
          : "KI generiert Demo-Code...")
      : (cfg?.label ?? "Demo wird vorbereitet...");

    return (
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 space-y-3">
        <div className="flex items-center gap-3">
          <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin flex-shrink-0" />
          <div>
            <p className="text-sm font-medium text-blue-700">Phase 2 läuft — Demo + E-Mail werden erstellt...</p>
            <p className="text-xs text-blue-500">{label}</p>
          </div>
        </div>
        <div className="space-y-1">
          <div className="w-full bg-blue-100 rounded-full h-2 overflow-hidden">
            <div
              className="h-2 rounded-full bg-blue-500 transition-all duration-1000 ease-out"
              style={{ width: `${pct}%` }}
            />
          </div>
          <p className="text-right text-xs text-blue-400">{pct}%</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border p-5 space-y-3">
      <h2 className="font-semibold text-xs text-gray-400 uppercase tracking-wide">Phase 2</h2>
      <p className="text-sm text-gray-600">
        Generiert eine individuelle Demo-Website + fertige Cold-Email für diesen Lead.
        Dauert ca. 2–3 Minuten. Kosten: ~$0.40.
      </p>
      <button
        onClick={handleGenerate}
        disabled={loading}
        className="w-full px-4 py-2.5 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 font-medium transition-colors disabled:opacity-60"
      >
        {loading ? "Starte..." : FAILED_STAGES.has(stage) ? "Erneut versuchen — Demo + E-Mail" : "Phase 2 starten — Demo + E-Mail"}
      </button>
      {error && <p className="text-red-500 text-xs">{error}</p>}
    </div>
  );
}
