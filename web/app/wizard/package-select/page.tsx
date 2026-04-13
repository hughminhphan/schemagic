"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import AppShell from "@/components/app/AppShell";
import AuthGate from "@/components/app/AuthGate";
import {
  useWizard,
  useWizardDispatch,
} from "@/components/app/WizardProvider";
import { useLicenseContext } from "@/components/app/LicenseContext";
import { apiBase, fetchWithLicense } from "@/lib/api-base";
import { Button, TerminalLine } from "@/components/ui";

function WizardPackageSelect() {
  const router = useRouter();
  const { candidates, jobId, step } = useWizard();
  const dispatch = useWizardDispatch();
  const { acquireToken } = useLicenseContext();
  const [selecting, setSelecting] = useState<string | null>(null);

  useEffect(() => {
    if (step === "PIN_REVIEW") {
      router.replace("/wizard/pin-review");
    } else if (step === "IDLE") {
      router.replace("/wizard/idle");
    }
  }, [step, router]);

  async function handleSelect(packageName: string) {
    const candidate = candidates.find((c) => c.name === packageName);
    if (!candidate || selecting) return;

    setSelecting(packageName);
    try {
      const token = await acquireToken();
      if (!token) return;
      const res = await fetchWithLicense(
        `${apiBase()}/api/select-package`,
        token,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ job_id: jobId, package: candidate }),
        },
      );
      if (!res.ok) throw new Error(`Server error (${res.status})`);
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
        message:
          err instanceof Error ? err.message : "Package selection failed",
      });
    } finally {
      setSelecting(null);
    }
  }

  return (
    <AppShell header="withBack" backHref="/wizard/idle">
      <div className="flex-1 flex items-center justify-center px-12 py-24">
        <div className="w-full max-w-3xl flex flex-col gap-12">
          <div className="flex flex-col gap-6">
            <TerminalLine>wizard/package-select</TerminalLine>
            <h1 className="font-sans text-h1 text-text-primary">
              Pick a package
            </h1>
            <p className="font-sans text-body text-text-secondary">
              Multiple package variants were detected. Choose the one you&apos;re
              using.
            </p>
          </div>

          {candidates.length === 0 ? (
            <p className="font-mono text-mono-xs text-text-secondary">
              No candidates available. Return to{" "}
              <button
                className="text-accent underline"
                onClick={() => router.push("/wizard/idle")}
              >
                start
              </button>
              .
            </p>
          ) : (
            <div className="flex flex-col">
              {candidates.map((c) => {
                const isSelecting = selecting === c.name;
                const disabled = selecting !== null;
                return (
                  <button
                    key={c.name}
                    onClick={() => handleSelect(c.name)}
                    disabled={disabled}
                    className={`
                      flex items-center justify-between
                      border border-border bg-surface-raised
                      h-[64px] px-6 mb-2 last:mb-0
                      text-left
                      hover:border-accent transition-colors
                      disabled:cursor-wait
                      ${isSelecting ? "border-accent" : ""}
                      ${disabled && !isSelecting ? "opacity-50" : ""}
                    `}
                  >
                    <span className="font-sans text-body text-text-primary">
                      {c.name}
                    </span>
                    <span className="font-mono text-mono-label text-text-secondary">
                      {isSelecting ? "extracting..." : `${c.pin_count} pins`}
                    </span>
                  </button>
                );
              })}
            </div>
          )}

          <Button
            variant="secondary"
            onClick={() => router.push("/wizard/idle")}
          >
            Cancel
          </Button>
        </div>
      </div>
    </AppShell>
  );
}

export default function WizardPackageSelectPage() {
  return (
    <AuthGate>
      <WizardPackageSelect />
    </AuthGate>
  );
}
