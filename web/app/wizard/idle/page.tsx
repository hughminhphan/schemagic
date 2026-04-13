"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import AppShell from "@/components/app/AppShell";
import AuthGate from "@/components/app/AuthGate";
import { useWizardDispatch } from "@/components/app/WizardProvider";
import { Button, Input, TerminalLine } from "@/components/ui";

function WizardIdle() {
  const router = useRouter();
  const dispatch = useWizardDispatch();
  const [part, setPart] = useState("");

  useEffect(() => {
    dispatch({ type: "RESET" });
  }, [dispatch]);

  const handleGenerate = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = part.trim();
    if (!trimmed) return;
    router.push(`/wizard/running?part=${encodeURIComponent(trimmed)}`);
  };

  return (
    <AppShell header="default">
      <div className="flex-1 flex items-center justify-center px-12 py-24">
        <form onSubmit={handleGenerate} className="w-full max-w-3xl flex flex-col gap-12">
          <div className="flex flex-col gap-6">
            <TerminalLine>wizard/idle</TerminalLine>
            <h1 className="font-sans text-h1 text-text-primary">
              Generate a KiCad part
            </h1>
            <p className="font-sans text-body text-text-secondary">
              Enter a manufacturer part number. We&apos;ll fetch the datasheet
              and build the symbol + footprint.
            </p>
          </div>

          <Input
            caret
            placeholder="LM358"
            autoFocus
            value={part}
            onChange={(e) => setPart(e.target.value)}
          />

          <Button type="submit" disabled={!part.trim()}>
            Generate
          </Button>
        </form>
      </div>
    </AppShell>
  );
}

export default function WizardIdlePage() {
  return (
    <AuthGate>
      <WizardIdle />
    </AuthGate>
  );
}
