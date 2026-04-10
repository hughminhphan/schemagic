"use client";

import { useState, type FormEvent } from "react";
import { useWizard, useWizardDispatch } from "./WizardProvider";
import { useLicenseContext } from "./LicenseContext";
import { apiBase, fetchWithLicense } from "@/lib/api-base";

export default function PartInput() {
  const [partNumber, setPartNumber] = useState("");
  const state = useWizard();
  const dispatch = useWizardDispatch();
  const { acquireToken } = useLicenseContext();

  const isRunning = state.step === "RUNNING";

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = partNumber.trim();
    if (!trimmed) return;

    try {
      // Acquire a license token before starting (pro: cached JWT, free: single-use)
      const token = await acquireToken();
      if (!token) return;

      const res = await fetchWithLicense(`${apiBase()}/api/run`, token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ part_number: trimmed }),
      });
      if (!res.ok) {
        const text = await res.text();
        let detail = `Server error (${res.status})`;
        try {
          const errJson = JSON.parse(text);
          const raw = errJson.detail ?? errJson.message ?? errJson.error;
          if (typeof raw === "string") detail = raw;
          else if (raw) detail = JSON.stringify(raw);
        } catch {
          if (text) detail = text;
        }
        throw new Error(detail);
      }
      const data = await res.json();
      const jobId = data.job_id;

      dispatch({ type: "START_RUN", jobId, partNumber: trimmed });

      // Detect KiCad project in parallel with pipeline
      fetch(`${apiBase()}/api/kicad-project`)
        .then((r) => r.json())
        .then((data) => {
          if (data.project_dir) {
            dispatch({
              type: "DETECT_PROJECT",
              project: { dir: data.project_dir, name: data.project_name || data.project_dir },
            });
          }
        })
        .catch(() => {}); // non-critical

      const sseRes = await fetch(`${apiBase()}/api/status/${jobId}`);
      if (!sseRes.ok || !sseRes.body) {
        dispatch({ type: "ERROR", message: "Failed to connect to status stream" });
        return;
      }

      const reader = sseRes.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      let currentEvent = "";

      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop()!;

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            const d = JSON.parse(line.slice(6));
            switch (currentEvent) {
              case "status":
                dispatch({ type: "ADD_LOG", message: d.message });
                break;
              case "complete":
                dispatch({
                  type: "COMPLETE",
                  datasheet: d.datasheet,
                  match: d.match,
                  pins: d.pins,
                  candidates: d.candidates || [],
                });
                return;
              case "error":
                dispatch({ type: "ERROR", message: typeof d.message === "string" ? d.message : JSON.stringify(d.message) });
                return;
            }
            currentEvent = "";
          }
        }
      }
    } catch (err) {
      dispatch({
        type: "ERROR",
        message: err instanceof Error ? err.message : String(err ?? "Failed to start pipeline"),
      });
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3">
      <input
        type="text"
        value={partNumber}
        onChange={(e) => setPartNumber(e.target.value)}
        placeholder="e.g. LM358, STM32F103C8T6, ATmega328P"
        disabled={isRunning}
        className={`
          w-full h-[48px] px-4 text-sm rounded-lg
          bg-surface-raised border border-border
          text-text-primary placeholder:text-text-secondary
          focus:outline-none focus:border-accent
          transition-colors
          ${isRunning ? "opacity-40 pointer-events-none" : ""}
        `}
      />

      <button
        type="submit"
        disabled={isRunning || !partNumber.trim()}
        className="bg-accent h-[48px] px-[24px] text-sm font-medium text-white rounded-lg hover:bg-accent-hover transition-colors disabled:opacity-40"
      >
        {isRunning ? "Running..." : "Generate"}
      </button>
    </form>
  );
}
