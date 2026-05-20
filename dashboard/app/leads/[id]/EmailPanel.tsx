"use client";
import { useState } from "react";
import { LeadDetail, approveEmail, updateStatus } from "@/lib/api";

export default function EmailPanel({ lead }: { lead: LeadDetail }) {
  const [approved, setApproved] = useState(lead.email_approved);
  const [variant, setVariant] = useState(lead.email_variant);
  const [status, setStatus] = useState(lead.status);

  const hasEmails = lead.email_body_a || lead.email_body_b;

  const mailto = (body: string) => {
    const s = encodeURIComponent(lead.email_subject || "Ihre Online-Praesenz in Berlin");
    const b = encodeURIComponent(body);
    return `mailto:${lead.email ?? ""}?subject=${s}&body=${b}`;
  };

  const handleApprove = async (v: "a" | "b") => {
    await approveEmail(lead.id, v);
    setApproved(true);
    setVariant(v);
    setStatus("contacted");
  };

  const handleStatus = async (s: string) => {
    await updateStatus(lead.id, s);
    setStatus(s);
  };

  return (
    <div className="space-y-4">
      {/* CRM */}
      <div className="bg-white rounded-xl p-5 border">
        <h2 className="font-semibold text-xs text-gray-400 uppercase tracking-wide mb-3">CRM Status</h2>
        <div className="flex gap-2 flex-wrap">
          {[
            { s: "new", label: "Neu", color: "bg-gray-100 text-gray-600" },
            { s: "contacted", label: "Kontaktiert", color: "bg-blue-100 text-blue-700" },
            { s: "replied", label: "Geantwortet", color: "bg-green-100 text-green-700" },
            { s: "closed", label: "Abgeschlossen", color: "bg-purple-100 text-purple-700" },
            { s: "ignored", label: "Ignoriert", color: "bg-gray-100 text-gray-400" },
          ].map(({ s, label, color }) => (
            <button
              key={s}
              onClick={() => handleStatus(s)}
              className={`px-3 py-1.5 text-xs rounded-lg font-medium transition-all ${
                status === s
                  ? `${color} ring-2 ring-offset-1 ring-current`
                  : "bg-gray-50 text-gray-500 hover:bg-gray-100"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Email */}
      {!hasEmails ? (
        <div className="bg-white rounded-xl p-5 border text-gray-400 text-sm text-center py-8">
          {!lead.email
            ? "Keine E-Mail-Adresse gefunden"
            : lead.stage !== "email_ready"
            ? `Warte auf Stage: ${lead.stage}`
            : "Kein Email generiert"}
        </div>
      ) : (
        <>
          {approved && (
            <div className="bg-green-50 border border-green-200 rounded-xl px-4 py-3 text-green-700 text-sm flex items-center gap-2">
              <span className="text-lg">✓</span>
              <span>Variante {variant?.toUpperCase()} freigegeben und versendet</span>
            </div>
          )}

          {(["a", "b"] as const).map((v) => {
            const body = v === "a" ? lead.email_body_a : lead.email_body_b;
            if (!body) return null;
            const isApproved = approved && variant === v;
            return (
              <div
                key={v}
                className={`bg-white rounded-xl border overflow-hidden ${isApproved ? "ring-2 ring-green-400" : ""}`}
              >
                <div className="px-5 pt-4 pb-2 border-b bg-gray-50 flex items-center justify-between">
                  <h3 className="font-semibold text-sm">
                    {v === "a" ? "Variante A — Problem-fokussiert" : "Variante B — Chance-fokussiert"}
                  </h3>
                  {isApproved && <span className="text-xs text-green-600 font-semibold">Gesendet</span>}
                </div>
                {lead.email_subject && (
                  <div className="px-5 py-2 border-b bg-gray-50 text-xs text-gray-500">
                    Betreff: <span className="text-gray-700 font-medium">{lead.email_subject}</span>
                  </div>
                )}
                <pre className="px-5 py-4 text-xs text-gray-700 whitespace-pre-wrap font-sans leading-relaxed max-h-56 overflow-y-auto">
                  {body}
                </pre>
                <div className="px-5 pb-4">
                  {!approved ? (
                    <a
                      href={mailto(body)}
                      onClick={() => handleApprove(v)}
                      className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 font-medium"
                    >
                      ✉ Diese senden
                    </a>
                  ) : !isApproved ? (
                    <span className="text-gray-300 text-xs">Andere Variante wurde gesendet</span>
                  ) : null}
                </div>
              </div>
            );
          })}
        </>
      )}
    </div>
  );
}
