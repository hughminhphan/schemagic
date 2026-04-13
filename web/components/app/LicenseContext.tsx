"use client";

import { createContext, useContext } from "react";
import type { LicenseStatus } from "@/lib/payments-types";

export type LicenseTier = "pro" | "free" | null;

export interface LicenseContextValue {
  email: string | null;
  status: LicenseStatus | null;
  tier: LicenseTier;
  loading: boolean;
  error: string | null;
  /** Set the user's email and trigger initial license check. Dev/legacy path. */
  setEmail: (email: string) => Promise<void>;
  /** Send a magic-link sign-in email. Resolves when the request has been queued. */
  requestMagicLink: (email: string) => Promise<void>;
  /** Open Stripe Checkout in the system browser. */
  requestCheckout: (email: string) => Promise<void>;
  /** Open Stripe Customer Portal in the system browser. */
  requestPortal: () => Promise<void>;
  /** Re-validate the license (e.g. after payment in browser). */
  refreshLicense: () => Promise<void>;
  /** Clear stored email and return to the email prompt. */
  clearEmail: () => void;
  /**
   * Get a valid license token for sidecar requests.
   * Pass `{ consume: true }` when starting a new generation (`/api/run`) —
   * this forces a fresh fetch and decrements the free-tier counter.
   * Default (`consume: false`) returns the cached token if still valid,
   * so wizard continuation calls (`/api/select-package`, `/api/finalize`)
   * don't burn additional credits.
   * Returns null if the user has hit the free limit or is not licensed.
   */
  acquireToken: (opts?: { consume?: boolean }) => Promise<string | null>;
}

export const LicenseContext = createContext<LicenseContextValue | null>(null);

export function useLicenseContext(): LicenseContextValue {
  const ctx = useContext(LicenseContext);
  if (!ctx) throw new Error("useLicenseContext must be used within LicenseGate");
  return ctx;
}
