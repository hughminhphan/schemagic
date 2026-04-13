"use client";

import { Suspense, useEffect, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import AppShell from "@/components/app/AppShell";
import AuthGate from "@/components/app/AuthGate";
import {
  useWizard,
  useWizardDispatch,
} from "@/components/app/WizardProvider";
import { useLicenseContext } from "@/components/app/LicenseContext";
import { apiBase, fetchWithLicense } from "@/lib/api-base";
import { Button, TerminalBlock, TerminalLine } from "@/components/ui";

function WizardRunning() {
  const router = useRouter();
  const params = useSearchParams();
  const part = params.get("part") ?? "";
  const state = useWizard();
  const dispatch = useWizardDispatch();
  const { acquireToken } = useLicenseContext();
  const startedRef = useRef(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [state.logs.length]);

  useEffect(() => {
    if (state.step === "PACKAGE_SELECT") {
      router.replace("/wizard/package-select");
    } else if (state.step === "PIN_REVIEW") {
      router.replace("/wizard/pin-review");
    }
  }, [state.step, router]);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;

    if (!part) {
      router.replace("/wizard/idle");
      return;
    }

    let cancelled = false;

    async function runPipeline() {
      try {
        const token = await acquireToken();
        if (!token) return;

        const res = await fetchWithLicense(`${apiBase()}/api/run`, token, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ part_number: part }),
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

        const { job_id: jobId } = await res.json();
        if (cancelled) return;
        dispatch({ type: "START_RUN", jobId, partNumber: part });

        fetch(`${apiBase()}/api/kicad-project`)
          .then((r) => r.json())
          .then((data) => {
            if (data.project_dir) {
              dispatch({
                type: "DETECT_PROJECT",
                project: {
                  dir: data.project_dir,
                  name: data.project_name || data.project_dir,
                },
              });
            }
          })
          .catch(() => {});

        const sseRes = await fetch(`${apiBase()}/api/status/${jobId}`);
        if (!sseRes.ok || !sseRes.body) {
          dispatch({
            type: "ERROR",
            message: "Failed to connect to status stream",
          });
          return;
        }

        const reader = sseRes.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        let currentEvent = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done || cancelled) break;

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
                  if (!d.pins || d.pins.length === 0) {
                    dispatch({
                      type: "ERROR",
                      message: `No pins extracted for ${part}. The part number may be wrong, or the datasheet format isn't supported yet.`,
                    });
                  } else {
                    dispatch({
                      type: "COMPLETE",
                      datasheet: d.datasheet,
                      match: d.match,
                      pins: d.pins,
                      candidates: d.candidates || [],
                    });
                  }
                  return;
                case "error":
                  dispatch({
                    type: "ERROR",
                    message:
                      typeof d.message === "string"
                        ? d.message
                        : JSON.stringify(d.message),
                  });
                  return;
              }
              currentEvent = "";
            }
          }
        }
      } catch (err) {
        if (cancelled) return;
        dispatch({
          type: "ERROR",
          message:
            err instanceof Error
              ? err.message
              : String(err ?? "Failed to start pipeline"),
        });
      }
    }

    runPipeline();

    return () => {
      cancelled = true;
    };
  }, [part, router, dispatch, acquireToken]);

  const isError = state.step === "ERROR";
  const displayPart = part || state.partNumber || "(unknown)";

  return (
    <AppShell header="withBack" backHref="/wizard/idle">
      <div className="flex-1 flex items-center justify-center px-12 py-24">
        <div className="w-full max-w-3xl flex flex-col gap-12">
          <div className="flex flex-col gap-6">
            <TerminalLine>wizard/running</TerminalLine>
            <h1 className="font-sans text-h1 text-text-primary">
              {isError ? "Generation failed" : "Generating..."}
            </h1>
            <p className="font-sans text-body text-text-secondary">
              Part: {displayPart}
            </p>
          </div>

          <TerminalBlock className="max-h-[288px] overflow-y-auto">
            {state.logs.length === 0 && !isError ? (
              <TerminalLine>
                <span className="animate-pulse">starting pipeline</span>
              </TerminalLine>
            ) : (
              state.logs.map((log, i) => (
                <TerminalLine key={i}>{log}</TerminalLine>
              ))
            )}
            {!isError && state.step === "RUNNING" && state.logs.length > 0 && (
              <TerminalLine>
                <span className="animate-pulse">working</span>
              </TerminalLine>
            )}
            <div ref={bottomRef} />
          </TerminalBlock>

          {isError && (
            <>
              <div className="border border-accent bg-accent/5 px-6 py-5">
                <p className="font-mono text-mono-label uppercase tracking-wider text-accent mb-2">
                  Error
                </p>
                <p className="font-mono text-mono-xs text-text-primary leading-relaxed">
                  {state.error || "extraction failed"}
                </p>
              </div>

              <div className="flex items-center gap-6">
                <Button onClick={() => router.push("/wizard/idle")}>
                  Try again
                </Button>
                <Button variant="secondary">Report issue</Button>
              </div>
            </>
          )}
        </div>
      </div>
    </AppShell>
  );
}

export default function WizardRunningPage() {
  return (
    <AuthGate>
      <Suspense fallback={null}>
        <WizardRunning />
      </Suspense>
    </AuthGate>
  );
}
