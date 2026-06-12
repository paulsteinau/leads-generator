"use client";
import { useState, useEffect } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const SECRET = process.env.NEXT_PUBLIC_API_SECRET ?? "";
const authHeaders = (): HeadersInit =>
  SECRET ? { Authorization: `Bearer ${SECRET}` } : {};

export default function SourcePanel({ leadId }: { leadId: number }) {
  const [jsx, setJsx] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [pasted, setPasted] = useState("");
  const [deploying, setDeploying] = useState(false);
  const [deployMsg, setDeployMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    fetch(`${API}/leads/${leadId}/demo-source`, { headers: authHeaders() })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { setJsx(d?.jsx ?? null); setLoading(false); })
      .catch(() => setLoading(false));
  }, [leadId]);

  function download() {
    if (!jsx) return;
    const blob = new Blob([jsx], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "App.jsx";
    a.click();
    URL.revokeObjectURL(url);
  }

  async function deploy() {
    const code = pasted.trim();
    if (!code) return;
    setDeploying(true);
    setDeployMsg(null);
    try {
      const r = await fetch(`${API}/leads/${leadId}/demo-source`, {
        method: "PUT",
        headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ jsx: code }),
      });
      const d = await r.json();
      if (r.ok) {
        setDeployMsg({ ok: true, text: `Deployed: ${d.demo_url ?? "ok"}` });
        setPasted("");
        setJsx(code);
      } else {
        setDeployMsg({ ok: false, text: d.detail ?? "Fehler" });
      }
    } catch (e) {
      setDeployMsg({ ok: false, text: "Netzwerkfehler" });
    } finally {
      setDeploying(false);
    }
  }

  if (loading) return null;
  if (!jsx) return null;

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-gray-300 mb-4">Quellcode</p>

      {/* Download */}
      <button
        onClick={download}
        className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-gray-50 hover:bg-gray-100 text-gray-700 text-sm font-medium transition-colors border border-gray-200"
      >
        <svg className="w-4 h-4" viewBox="0 0 16 16" fill="none">
          <path d="M8 2v8m0 0l-3-3m3 3l3-3M3 12h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
        App.jsx herunterladen
      </button>

      {/* Deploy section */}
      <div className="mt-4 pt-4 border-t border-gray-50">
        <button
          onClick={() => setOpen((v) => !v)}
          className="w-full flex items-center justify-between text-xs text-gray-400 hover:text-gray-600 transition-colors mb-2"
        >
          <span>Geänderten Code deployen</span>
          <svg className={`w-3.5 h-3.5 transition-transform ${open ? "rotate-180" : ""}`} viewBox="0 0 12 12" fill="none">
            <path d="M3 4.5l3 3 3-3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>

        {open && (
          <>
            <textarea
              value={pasted}
              onChange={(e) => setPasted(e.target.value)}
              placeholder="Bearbeiteten App.jsx Code hier einfügen…"
              className="w-full h-40 text-xs font-mono bg-gray-50 border border-gray-200 rounded-xl p-3 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-200 text-gray-700 placeholder-gray-300"
            />
            <button
              onClick={deploy}
              disabled={deploying || !pasted.trim()}
              className="mt-2 w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-100 disabled:text-gray-300 text-white text-sm font-medium transition-colors"
            >
              {deploying ? (
                <>
                  <svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 12 12" fill="none"><circle cx="6" cy="6" r="4.5" stroke="currentColor" strokeWidth="1.5" strokeDasharray="14 8"/></svg>
                  Wird deployed…
                </>
              ) : "Speichern & Deployen"}
            </button>
            {deployMsg && (
              <p className={`mt-2 text-xs text-center ${deployMsg.ok ? "text-green-600" : "text-red-500"}`}>
                {deployMsg.text}
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
