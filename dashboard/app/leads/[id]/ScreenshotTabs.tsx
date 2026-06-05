"use client";
import { useState } from "react";

interface Props {
  shots: string[];
  labels: string[];
}

export default function ScreenshotTabs({ shots, labels }: Props) {
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
      <code className="block text-xs text-gray-500 bg-gray-50 rounded-lg px-3 py-2 break-all">
        {shots[active]}
      </code>
    </div>
  );
}
