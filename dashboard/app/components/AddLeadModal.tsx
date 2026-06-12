"use client";
import { useState } from "react";
import { createManualLead } from "@/lib/api";

interface Props {
  onClose: () => void;
  onCreated: (id: number) => void;
}

const PROJECT_TYPES = [
  {
    value: "new_website",
    label: "Neue Website",
    desc: "Komplett neuer Webauftritt von Grund auf",
  },
  {
    value: "redesign",
    label: "Website überarbeiten",
    desc: "Bestehende Website modernisieren & verbessern",
  },
];

export default function AddLeadModal({ onClose, onCreated }: Props) {
  const [form, setForm] = useState({
    name: "", website: "", category: "", district: "",
    phone: "", email: "", lead_tier: "warm", notes: "", project_type: "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) { setError("Name ist Pflichtfeld"); return; }
    setLoading(true);
    setError(null);
    const result = await createManualLead({
      ...form,
      website: form.website || undefined,
      category: form.category || undefined,
      district: form.district || undefined,
      phone: form.phone || undefined,
      email: form.email || undefined,
      notes: form.notes || undefined,
      project_type: form.project_type || undefined,
    });
    setLoading(false);
    if (result.ok && result.id) {
      onCreated(result.id);
    } else {
      setError(result.error || "Fehler beim Erstellen");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6 space-y-4" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Lead manuell hinzufügen</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">Projektart</label>
            <div className="mt-1.5 grid grid-cols-2 gap-2">
              {PROJECT_TYPES.map((pt) => (
                <button
                  key={pt.value}
                  type="button"
                  onClick={() => set("project_type", pt.value)}
                  className={`text-left px-3.5 py-3 rounded-xl border-2 transition-all ${
                    form.project_type === pt.value
                      ? "border-indigo-500 bg-indigo-50"
                      : "border-gray-200 hover:border-gray-300"
                  }`}
                >
                  <p className={`text-sm font-semibold ${form.project_type === pt.value ? "text-indigo-700" : "text-gray-700"}`}>
                    {pt.label}
                  </p>
                  <p className="text-[11px] text-gray-400 mt-0.5 leading-snug">{pt.desc}</p>
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">Name *</label>
            <input value={form.name} onChange={e => set("name", e.target.value)}
              className="mt-1 w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
              placeholder="z.B. Zahnarztpraxis Müller" />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">Website</label>
            <input value={form.website} onChange={e => set("website", e.target.value)}
              className="mt-1 w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
              placeholder="https://..." />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">Kategorie</label>
              <input value={form.category} onChange={e => set("category", e.target.value)}
                className="mt-1 w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                placeholder="z.B. Zahnarzt" />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">Bezirk</label>
              <input value={form.district} onChange={e => set("district", e.target.value)}
                className="mt-1 w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                placeholder="z.B. Mitte" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">Telefon</label>
              <input value={form.phone} onChange={e => set("phone", e.target.value)}
                className="mt-1 w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                placeholder="+49 30 ..." />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">E-Mail</label>
              <input value={form.email} onChange={e => set("email", e.target.value)}
                className="mt-1 w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                placeholder="info@..." />
            </div>
          </div>
          <div>
            <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">Bewertung</label>
            <select value={form.lead_tier} onChange={e => set("lead_tier", e.target.value)}
              className="mt-1 w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400">
              <option value="hot">Hot — Website sehr schwach</option>
              <option value="warm">Warm — Website verbesserungswürdig</option>
              <option value="low">Low — nur zur Vollständigkeit</option>
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">Notiz</label>
            <input value={form.notes} onChange={e => set("notes", e.target.value)}
              className="mt-1 w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
              placeholder="Warum ist dieser Lead interessant?" />
          </div>
          {error && <p className="text-red-500 text-xs">{error}</p>}
          <button type="submit" disabled={loading}
            className="w-full py-2.5 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 font-medium transition-colors disabled:opacity-60">
            {loading ? "Wird hinzugefügt..." : "Lead hinzufügen"}
          </button>
        </form>
      </div>
    </div>
  );
}
