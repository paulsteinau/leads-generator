"use client";
import { useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Props {
  shots: string[];
  labels: string[];
  leadId: number;
}

export default function ScreenshotTabs({ shots, labels, leadId }: Props) {
  const [active, setActive] = useState(0);

  return (
    <div>
      <div className="flex gap-1.5 flex-wrap mb-3">
        {shots.map((_, i) => (
          <button
            key={i}
            onClick={() => setActive(i)}
            className={`px-3 py-1.5 text-xs rounded-lg font-medium transition-colors ${
              active === i
                ? "bg-blue-600 text-white"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            {labels[i] ?? `Screenshot ${i + 1}`}
          </button>
        ))}
      </div>
      <img
        src={`${API}/leads/${leadId}/screenshots/${active}`}
        alt={labels[active] ?? `Screenshot ${active + 1}`}
        className="w-full rounded-lg border border-gray-100"
      />
    </div>
  );
}
