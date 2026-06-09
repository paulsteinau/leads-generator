"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import AddLeadModal from "./AddLeadModal";

export default function AddLeadButton() {
  const [open, setOpen] = useState(false);
  const router = useRouter();

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 px-3.5 py-2 text-sm text-white bg-indigo-600 rounded-xl hover:bg-indigo-700 transition-colors font-medium shadow-sm"
      >
        <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none">
          <path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
        </svg>
        Lead hinzufügen
      </button>
      {open && (
        <AddLeadModal
          onClose={() => setOpen(false)}
          onCreated={(id) => {
            setOpen(false);
            router.push(`/leads/${id}`);
          }}
        />
      )}
    </>
  );
}
