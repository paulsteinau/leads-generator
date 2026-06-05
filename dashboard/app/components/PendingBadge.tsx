"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { getPendingReview } from "@/lib/api";

export default function PendingBadge() {
  const [count, setCount] = useState(0);

  useEffect(() => {
    const fetch = () => {
      getPendingReview()
        .then((data) => setCount(data.count))
        .catch(() => {});
    };
    fetch();
    const interval = setInterval(fetch, 30_000);
    return () => clearInterval(interval);
  }, []);

  if (count === 0) return null;

  return (
    <Link
      href="/leads?stage=ready_for_review"
      className="inline-flex items-center gap-1.5 px-3 py-1 bg-yellow-100 text-yellow-800 text-xs font-semibold rounded-full hover:bg-yellow-200 transition-colors"
    >
      <span className="w-2 h-2 bg-yellow-500 rounded-full animate-pulse" />
      {count} zur Freigabe
    </Link>
  );
}
