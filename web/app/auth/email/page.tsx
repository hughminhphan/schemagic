"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import AppShell from "@/components/app/AppShell";
import { useLicense } from "@/hooks/useLicense";
import { Button, Input, TerminalLine } from "@/components/ui";

export default function AuthEmailPage() {
  const router = useRouter();
  const license = useLicense();
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (license.loading) return;
    if (license.email && license.tier) {
      router.replace("/wizard/idle");
    }
  }, [license.loading, license.email, license.tier, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const trimmed = email.trim();
    if (!trimmed || !trimmed.includes("@")) {
      setError("Enter a valid email address.");
      return;
    }
    setSubmitting(true);
    try {
      await license.setEmail(trimmed);
      router.replace("/wizard/idle");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed.");
      setSubmitting(false);
    }
  };

  return (
    <AppShell header="wordmarkOnly">
      <div className="flex-1 flex items-center justify-center px-12 py-24">
        <form onSubmit={handleSubmit} className="w-full max-w-2xl flex flex-col gap-12">
          <div className="flex flex-col gap-6">
            <TerminalLine>auth/email</TerminalLine>
            <h1 className="font-sans text-h1 text-text-primary">
              Sign in
            </h1>
            <p className="font-sans text-body text-text-secondary">
              Enter your email. We&apos;ll send you a magic link to sign in.
            </p>
          </div>

          <Input
            caret
            placeholder="you@example.com"
            type="email"
            autoFocus
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            error={error ?? undefined}
            disabled={submitting}
          />

          <Button type="submit" disabled={submitting}>
            {submitting ? "Signing in..." : "Continue"}
          </Button>
        </form>
      </div>
    </AppShell>
  );
}
