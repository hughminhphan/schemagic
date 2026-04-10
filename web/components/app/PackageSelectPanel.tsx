"use client";

import { useState } from "react";
import { useWizard, useWizardDispatch } from "./WizardProvider";
import { apiBase } from "@/lib/api-base";

export default function PackageSelectPanel() {
  const { candidates, jobId } = useWizard();
  const dispatch = useWizardDispatch();
  const [selecting, setSelecting] = useState<string | null>(null);

  async function handleSelect(packageName: string) {
    const candidate = candidates.find((c) => c.name === packageName);
    if (!candidate || selecting) return;

    setSelecting(packageName);
    try {
      const res = await fetch(`${apiBase()}/api/select-package`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: jobId, package: candidate }),
      });
      const data = await res.json();
      dispatch({
        type: "SWITCH_PACKAGE",
        datasheet: data.datasheet,
        match: data.match,
        pins: data.pins,
      });
    } catch (err) {
      dispatch({
        type: "ERROR",
        message: err instanceof Error ? err.message : "Package selection failed",
      });
    } finally {
      setSelecting(null);
    }
  }

  return (
    <div className="mt-[48px]">
      <p className="font-mono text-xs text-text-secondary uppercase tracking-wider mb-[16px]">
        Multiple packages found
      </p>
      <p className="text-sm text-text-secondary mb-[24px]">
        This part has multiple package options. Select one to extract pin assignments.
      </p>

      <div className="space-y-[8px]">
        {candidates.map((c) => (
          <button
            key={c.name}
            onClick={() => handleSelect(c.name)}
            disabled={selecting !== null}
            className={`
              w-full flex items-center justify-between
              border border-border bg-surface-raised
              h-[56px] px-[24px]
              text-left
              hover:border-accent transition-colors
              disabled:opacity-50
              ${selecting === c.name ? "border-accent" : ""}
            `}
          >
            <span className="font-mono text-sm text-text-primary">
              {c.name}
            </span>
            <span className="text-xs text-text-secondary">
              {c.pin_count} pins
              {selecting === c.name && " - extracting..."}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
