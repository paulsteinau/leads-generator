"use client";
import { useState } from "react";
import { LeadDetail, approveLead, rejectLead, editDemo } from "@/lib/api";

export default function ReviewPanel({ lead }: { lead: LeadDetail }) {
  const subjects: string[] = (() => {
    try {
      return lead.email_subjects ? (JSON.parse(lead.email_subjects) as string[]) : [];
    } catch {
      return [];
    }
  })();

  const [selectedSubject, setSelectedSubject] = useState(0);
  const [body, setBody] = useState(lead.email_body_a ?? "");
  const [modalOpen, setModalOpen] = useState(false);
  const [editDescription, setEditDescription] = useState("");
  const [editLoading, setEditLoading] = useState(false);
  const [approveState, setApproveState] = useState<"idle" | "loading" | "sent" | "error">("idle");
  const [rejectState, setRejectState] = useState<"idle" | "loading" | "rejected">("idle");

  const handleApprove = async () => {
    setApproveState("loading");
    try {
      const result = await approveLead(lead.id);
      setApproveState(result.ok ? "sent" : "error");
    } catch {
      setApproveState("error");
    }
  };

  const handleReject = async () => {
    setRejectState("loading");
    try {
      await rejectLead(lead.id);
      setRejectState("rejected");
    } catch {
      setRejectState("idle");
    }
  };

  const handleEditSubmit = async () => {
    if (!editDescription.trim()) return;
    setEditLoading(true);
    try {
      await editDemo(lead.id, editDescription);
    } finally {
      setEditLoading(false);
      setModalOpen(false);
      setEditDescription("");
    }
  };

  if (rejectState === "rejected") {
    return (
      <div className="bg-white rounded-xl p-5 border">
        <p className="text-gray-500 text-sm text-center py-4">Abgelehnt</p>
      </div>
    );
  }

  if (approveState === "sent") {
    return (
      <div className="bg-green-50 border border-green-200 rounded-xl p-5">
        <p className="text-green-700 text-sm font-medium text-center">Gesendet!</p>
      </div>
    );
  }

  return (
    <>
      <div className="bg-white rounded-xl p-5 border space-y-4">
        <h2 className="font-semibold text-xs text-gray-400 uppercase tracking-wide">Review</h2>

        {/* Subject picker */}
        {subjects.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs text-gray-500 font-medium">Betreff</p>
            {subjects.map((subject, i) => (
              <label key={i} className="flex items-start gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="subject"
                  value={i}
                  checked={selectedSubject === i}
                  onChange={() => setSelectedSubject(i)}
                  className="mt-0.5 shrink-0"
                />
                <span className="text-xs text-gray-700 leading-relaxed">{subject}</span>
              </label>
            ))}
          </div>
        )}

        {/* Body textarea */}
        <div className="space-y-1">
          <p className="text-xs text-gray-500 font-medium">Nachricht</p>
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={8}
            className="w-full border rounded-lg px-3 py-2 text-xs text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-400 resize-y font-sans leading-relaxed"
          />
        </div>

        {/* Demo URL */}
        {lead.demo_url && (
          <div className="space-y-1">
            <p className="text-xs text-gray-500 font-medium">Demo-URL</p>
            <a
              href={lead.demo_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 text-xs hover:underline break-all block"
            >
              {lead.demo_url}
            </a>
          </div>
        )}

        {/* Actions */}
        <div className="flex flex-col gap-2 pt-1">
          <button
            onClick={() => setModalOpen(true)}
            className="w-full px-4 py-2 bg-gray-100 text-gray-700 text-sm rounded-lg hover:bg-gray-200 font-medium transition-colors"
          >
            Demo bearbeiten
          </button>

          <button
            onClick={handleApprove}
            disabled={approveState === "loading"}
            className="w-full px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 font-medium transition-colors disabled:opacity-60"
          >
            {approveState === "loading" ? "Wird gesendet..." : "Freigeben & Senden"}
          </button>

          {approveState === "error" && (
            <p className="text-red-500 text-xs text-center">Fehler beim Senden. Erneut versuchen.</p>
          )}

          <button
            onClick={handleReject}
            disabled={rejectState === "loading"}
            className="w-full px-4 py-2 bg-red-50 text-red-600 text-sm rounded-lg hover:bg-red-100 font-medium transition-colors disabled:opacity-60"
          >
            {rejectState === "loading" ? "..." : "Ablehnen"}
          </button>
        </div>
      </div>

      {/* Edit Demo Modal */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl p-6 w-full max-w-md shadow-xl space-y-4 mx-4">
            <h3 className="font-semibold text-gray-900">Demo bearbeiten</h3>
            <p className="text-xs text-gray-500">Beschreibe was geandert werden soll</p>
            <textarea
              value={editDescription}
              onChange={(e) => setEditDescription(e.target.value)}
              rows={5}
              autoFocus
              className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 resize-y"
              placeholder="z.B. Farbe des Buttons auf Grun andern, Telefonnummer aktualisieren..."
            />
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => { setModalOpen(false); setEditDescription(""); }}
                className="px-4 py-2 bg-gray-100 text-gray-600 text-sm rounded-lg hover:bg-gray-200"
              >
                Abbrechen
              </button>
              <button
                onClick={handleEditSubmit}
                disabled={editLoading || !editDescription.trim()}
                className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 font-medium disabled:opacity-60"
              >
                {editLoading ? "Wird gesendet..." : "Senden"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
