// dashboard/app/leads/[id]/GenerateDemoButton.tsx
"use client";
import { useState, useEffect, useCallback } from "react";
import { generateDemo, getDemoStatus } from "@/lib/api";

interface Props {
  leadId: number;
  initialStage: string;
  initialDemoUrl: string | null;
}

const GENERATING_STAGES = new Set(["generating_demo"]);
const DONE_STAGES = new Set(["ready_for_review", "approved", "rejected"]);

export default function GenerateDemoButton({ leadId, initialStage, initialDemoUrl }: Props) {
  const [stage, setStage] = useState(initialStage);
  const [demoUrl, setDemoUrl] = useState(initialDemoUrl);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const poll = useCallback(async () => {
    const status = await getDemoStatus(leadId);
    setStage(status.stage);
    if (status.demo_url) setDemoUrl(status.demo_url);
    return status;
  }, [leadId]);

  useEffect(() => {
    if (!GENERATING_STAGES.has(stage)) return;
    const interval = setInterval(async () => {
      const status = await poll();
      if (!GENERATING_STAGES.has(status.stage)) {
        clearInterval(interval);
        if (status.ready || status.demo_url) {
          window.location.reload(); // refresh to show ReviewPanel + demo iframe
        }
      }
    }, 4000);
    return () => clearInterval(interval);
  }, [stage, poll]);

  const handleGenerate = async () => {
    setLoading(true);
    setError(null);
    const result = await generateDemo(leadId);
    if (result.ok) {
      setStage("generating_demo");
    } else {
      setError(result.error || "Fehler beim Starten");
    }
    setLoading(false);
  };

  if (demoUrl || DONE_STAGES.has(stage)) return null;

  if (GENERATING_STAGES.has(stage)) {
    return (
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 flex items-center gap-3">
        <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        <div>
          <p className="text-sm font-medium text-blue-700">Phase 2 läuft — Demo + E-Mail werden erstellt...</p>
          <p className="text-xs text-blue-500">Website scrapen → KI-Demo generieren → Vercel-Deploy → E-Mail schreiben</p>
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
        {loading ? "Starte..." : "Phase 2 starten — Demo + E-Mail"}
      </button>
      {error && <p className="text-red-500 text-xs">{error}</p>}
      {stage === "demo_failed" && (
        <p className="text-orange-500 text-xs">Letzter Versuch fehlgeschlagen. Erneut versuchen?</p>
      )}
    </div>
  );
}
