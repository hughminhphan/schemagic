"use client";

import { useState } from "react";

export default function Pricing() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleCheckout() {
    const trimmed = email.trim().toLowerCase();
    if (!trimmed || !trimmed.includes("@")) {
      setError("Enter a valid email address.");
      return;
    }
    setLoading(true);
    setError("");

    try {
      const res = await fetch("/api/payments/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: trimmed }),
      });
      const data = await res.json();
      if (data.url) {
        window.location.href = data.url;
      } else {
        setError(data.error || "Something went wrong. Try again.");
      }
    } catch {
      setError("Could not reach the server. Try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section id="pricing" className="border-t border-border">
      <div className="mx-auto max-w-6xl px-6 py-[96px]">
        <h2 className="text-3xl font-bold tracking-tight md:text-4xl">
          Pricing
        </h2>
        <p className="mt-[24px] text-text-secondary max-w-xl">
          3 free generations to try it out. Then one simple plan.
        </p>

        <div className="mt-[48px] flex flex-col md:flex-row gap-[48px]">
          {/* Free tier */}
          <div className="border border-border p-[48px] flex-1">
            <p className="font-mono text-xs text-text-secondary uppercase tracking-wider">
              Free
            </p>
            <p className="mt-[24px] text-4xl font-bold">$0</p>
            <ul className="mt-[24px] space-y-[12px] text-sm text-text-secondary">
              <li>3 symbol + footprint generations</li>
              <li>Full pin review and editing</li>
              <li>Any manufacturer, any part</li>
            </ul>
            <a
              href="/api/download/mac"
              className="mt-[48px] inline-block border border-border px-[24px] py-[12px] text-sm font-medium hover:bg-surface-raised transition-colors"
            >
              Download free
            </a>
          </div>

          {/* Pro tier */}
          <div className="border border-accent/40 p-[48px] flex-1">
            <p className="font-mono text-xs text-accent uppercase tracking-wider">
              Pro
            </p>
            <p className="mt-[24px] text-4xl font-bold">
              $5<span className="text-lg font-normal text-text-secondary"> USD/month</span>
            </p>
            <ul className="mt-[24px] space-y-[12px] text-sm text-text-secondary">
              <li>Unlimited generations</li>
              <li>7-day offline access</li>
              <li>Full pin review and editing</li>
              <li>Any manufacturer, any part</li>
            </ul>
            <div className="mt-[48px]">
              <div className="flex flex-col sm:flex-row gap-[12px]">
                <input
                  type="email"
                  placeholder="you@email.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleCheckout();
                  }}
                  className="bg-surface border border-border px-[16px] py-[12px] text-sm text-text-primary placeholder:text-text-secondary/50 outline-none focus:border-accent/60 transition-colors flex-1"
                />
                <button
                  onClick={handleCheckout}
                  disabled={loading}
                  className="bg-accent hover:bg-accent-hover text-white px-[24px] py-[12px] text-sm font-medium transition-colors disabled:opacity-50 whitespace-nowrap"
                >
                  {loading ? "Redirecting..." : "Subscribe"}
                </button>
              </div>
              {error && (
                <p className="mt-[12px] text-sm text-accent">{error}</p>
              )}
              <p className="mt-[12px] font-mono text-xs text-text-secondary">
                Secure checkout via Stripe. Cancel anytime.
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
