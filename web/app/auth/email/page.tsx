"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import AppShell from "@/components/app/AppShell";
import { useLicense } from "@/hooks/useLicense";
import { Button, Input, TerminalLine } from "@/components/ui";

type View = "form" | "sent";

export default function AuthEmailPage() {
  const router = useRouter();
  const license = useLicense();
  const [email, setEmail] = useState("");
  const [sentTo, setSentTo] = useState("");
  const [view, setView] = useState<View>("form");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isDev = process.env.NODE_ENV !== "production";

  useEffect(() => {
    if (license.loading) return;
    if (!license.email) return;
    if (license.tier) {
      router.replace("/wizard/idle");
    } else if (
      license.status &&
      license.status.generationsUsed >= license.status.generationsLimit
    ) {
      router.replace("/auth/paywall");
    }
  }, [
    license.loading,
    license.email,
    license.tier,
    license.status,
    router,
  ]);

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
      await license.requestMagicLink(trimmed);
      setSentTo(trimmed);
      setView("sent");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send magic link.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDevSignIn = async () => {
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
      setError(err instanceof Error ? err.message : "Dev sign-in failed.");
      setSubmitting(false);
    }
  };

  const handleSendAnother = () => {
    setView("form");
    setError(null);
  };

  return (
    <AppShell header="wordmarkOnly">
      <div className="flex-1 flex items-center justify-center px-12 py-24">
        <div className="w-full max-w-2xl flex flex-col gap-12">
          <div className="flex flex-col gap-6">
            <TerminalLine>auth/email</TerminalLine>
            {view === "form" ? (
              <>
                <h1 className="font-sans text-h1 text-text-primary">
                  Enter your email
                </h1>
                <p className="font-sans text-body text-text-secondary">
                  Sign in to start generating KiCad symbols.
                </p>
              </>
            ) : (
              <>
                <h1 className="font-sans text-h1 text-text-primary">
                  Check your inbox
                </h1>
                <p className="font-sans text-body text-text-secondary">
                  We sent a sign-in link to{" "}
                  <span className="text-text-primary">{sentTo}</span>. It
                  expires in 15 minutes.
                </p>
              </>
            )}
          </div>

          {view === "form" ? (
            <form onSubmit={handleSubmit} className="flex flex-col gap-12">
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

              <div className="flex items-center justify-end gap-6">
                <Button type="submit" disabled={submitting || !email.trim()}>
                  {submitting ? "Sending..." : "Enter  →"}
                </Button>
              </div>

              {isDev ? (
                <button
                  type="button"
                  onClick={handleDevSignIn}
                  disabled={submitting}
                  className="self-start font-mono text-mono-xs uppercase tracking-wide text-text-secondary hover:text-accent disabled:opacity-40"
                >
                  Dev sign-in (skip magic link)
                </button>
              ) : null}
            </form>
          ) : (
            <div className="flex items-center gap-6">
              <Button variant="secondary" onClick={handleSendAnother}>
                Send another link
              </Button>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
