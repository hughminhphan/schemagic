"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Nav from "@/components/Nav";

export default function ActivatePage() {
  return (
    <Suspense
      fallback={
        <div className="grid-bg min-h-screen flex items-center justify-center">
          <p className="font-mono text-xs text-text-secondary animate-pulse">
            Loading...
          </p>
        </div>
      }
    >
      <ActivateContent />
    </Suspense>
  );
}

function ActivateContent() {
  const params = useSearchParams();
  const sessionId = params.get("session_id");
  const [status, setStatus] = useState<"loading" | "success" | "error">(
    "loading"
  );

  useEffect(() => {
    if (!sessionId) {
      setStatus("success");
      return;
    }
    // We don't need to verify the session server-side here.
    // The app will call /api/license/validate on next launch,
    // which checks Stripe subscription status directly.
    setStatus("success");
  }, [sessionId]);

  return (
    <div className="grid-bg min-h-screen">
      <Nav />
      <main className="mx-auto max-w-6xl px-6 py-[96px]">
        <div className="mb-[48px]">
          <h1 className="text-3xl font-bold tracking-tight">
            sche<span className="text-accent">MAGIC</span>
          </h1>
        </div>
        <div className="border border-border bg-surface-raised p-[24px] max-w-md">
          {status === "loading" && (
            <p className="font-mono text-xs text-text-secondary animate-pulse">
              Verifying payment...
            </p>
          )}
          {status === "success" && (
            <>
              <p className="font-mono text-xs text-accent uppercase tracking-wider mb-[12px]">
                Subscription active
              </p>
              <p className="text-sm text-text-secondary mb-[24px]">
                Your subscription is now active. Open scheMAGIC and it will
                activate automatically.
              </p>
              <p className="text-xs text-text-secondary">
                If the app doesn't activate immediately, click "Already
                subscribed? Refresh" on the paywall screen.
              </p>
            </>
          )}
          {status === "error" && (
            <>
              <p className="font-mono text-xs text-red-400 uppercase tracking-wider mb-[12px]">
                Something went wrong
              </p>
              <p className="text-sm text-text-secondary">
                Please contact support if your payment was processed but the app
                didn't activate.
              </p>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
