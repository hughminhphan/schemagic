"use client";

import { useLicenseContext } from "./LicenseContext";

export default function LicenseBadge() {
  const { status, tier } = useLicenseContext();
  if (!status) return null;

  if (tier === "pro") {
    return (
      <span className="inline-flex items-center px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider text-accent border border-accent/30 rounded">
        Pro
      </span>
    );
  }

  const remaining = status.generationsLimit - status.generationsUsed;
  return (
    <span className="inline-flex items-center px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider text-text-secondary border border-border rounded">
      {remaining}/{status.generationsLimit} free
    </span>
  );
}
