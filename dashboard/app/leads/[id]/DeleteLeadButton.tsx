"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { deleteLead } from "@/lib/api";

export default function DeleteLeadButton({ leadId }: { leadId: number }) {
  const router = useRouter();
  const [confirm, setConfirm] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleDelete = async () => {
    setLoading(true);
    const r = await deleteLead(leadId);
    if (r.ok) router.push("/");
    else { setLoading(false); setConfirm(false); alert("Fehler beim Löschen"); }
  };

  if (confirm) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-xs text-gray-500">Wirklich löschen?</span>
        <button
          onClick={handleDelete}
          disabled={loading}
          className="h-7 px-3 rounded-lg text-xs font-semibold bg-red-600 text-white hover:bg-red-500 disabled:opacity-50 transition-colors"
        >
          {loading ? "..." : "Ja, löschen"}
        </button>
        <button
          onClick={() => setConfirm(false)}
          className="h-7 px-3 rounded-lg text-xs text-gray-500 hover:bg-gray-100 transition-colors"
        >
          Abbrechen
        </button>
      </div>
    );
  }

  return (
    <button
      onClick={() => setConfirm(true)}
      className="h-7 px-3 rounded-lg text-xs font-medium text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors"
    >
      Lead entfernen
    </button>
  );
}
