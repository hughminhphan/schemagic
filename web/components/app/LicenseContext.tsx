"use client";

import { createContext, useContext } from "react";
import type { LicenseStatus } from "@/lib/payments-types";

export interface LicenseContextValue {
  email: string | null;
  status: LicenseStatus | null;
  loading: boolean;
  error: string | null;
  setEmail: (email: string) => Promise<void>;
  requestCheckout: (email: string) => Promise<void>;
  requestPortal: () => Promise<void>;
  consumeGeneration: () => Promise<boolean>;
  refreshLicense: () => Promise<void>;
}

export const LicenseContext = createContext<LicenseContextValue | null>(null);

export function useLicenseContext(): LicenseContextValue {
  const ctx = useContext(LicenseContext);
  if (!ctx) throw new Error("useLicenseContext must be used within LicenseGate");
  return ctx;
}
