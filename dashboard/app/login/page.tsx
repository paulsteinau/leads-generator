"use client";
import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

function LoginForm() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const params = useSearchParams();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json();
      if (data.ok) {
        const from = params.get("from") ?? "/";
        router.push(from);
        router.refresh();
      } else {
        setError(data.error ?? "Anmeldung fehlgeschlagen");
      }
    } catch {
      setError("Verbindungsfehler. Bitte erneut versuchen.");
    }
    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-[#080A12] flex items-center justify-center p-4 relative overflow-hidden">
      {/* Ambient glow */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[400px] bg-indigo-600/10 blur-[120px] rounded-full pointer-events-none" />
      <div className="absolute bottom-0 right-1/4 w-[400px] h-[300px] bg-violet-600/8 blur-[100px] rounded-full pointer-events-none" />

      <div className="relative w-full max-w-[380px]">
        {/* Logo */}
        <div className="flex justify-center mb-10">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-600 flex items-center justify-center shadow-lg shadow-indigo-600/30">
              <span className="text-white font-bold text-lg leading-none">B</span>
            </div>
            <div>
              <p className="text-white font-semibold text-lg leading-none tracking-tight">BerlinLeads</p>
              <p className="text-white/30 text-xs mt-0.5">Lead Management</p>
            </div>
          </div>
        </div>

        {/* Card — double-bezel */}
        <div className="bg-white/[0.03] rounded-[20px] p-[1.5px] ring-1 ring-white/8">
          <div className="bg-white/[0.04] backdrop-blur-md rounded-[18.5px] p-8 shadow-[inset_0_1px_1px_rgba(255,255,255,0.06)]">
            <h1 className="text-white font-semibold text-[17px] mb-1">Willkommen zurück</h1>
            <p className="text-white/35 text-sm mb-7">Melde dich mit deinen Zugangsdaten an</p>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-[0.1em] text-white/40 mb-2 block">
                  Benutzername
                </label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  autoComplete="username"
                  autoFocus
                  className="w-full bg-white/5 border border-white/8 rounded-xl px-4 py-3 text-white text-sm placeholder-white/15 focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500/40 transition-all duration-200"
                  placeholder="admin"
                />
              </div>

              <div>
                <label className="text-[11px] font-semibold uppercase tracking-[0.1em] text-white/40 mb-2 block">
                  Passwort
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                  className="w-full bg-white/5 border border-white/8 rounded-xl px-4 py-3 text-white text-sm placeholder-white/15 focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500/40 transition-all duration-200"
                  placeholder="••••••••"
                />
              </div>

              {error && (
                <div className="bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3">
                  <p className="text-red-400 text-sm">{error}</p>
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                className="w-full mt-2 bg-indigo-600 hover:bg-indigo-500 active:scale-[0.98] text-white font-semibold text-sm py-3 rounded-xl transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-indigo-600/20"
              >
                {loading ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    Anmelden...
                  </span>
                ) : (
                  "Anmelden"
                )}
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
