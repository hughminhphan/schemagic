"use client";

import { type ReactNode } from "react";
import { useLicense } from "@/hooks/useLicense";
import { LicenseContext } from "./LicenseContext";
import EmailPrompt from "./EmailPrompt";
import Paywall from "./Paywall";

interface Props {
  children: ReactNode;
}

export default function LicenseGate({ children }: Props) {
  const license = useLicense();

  if (license.loading) {
    return (
      <div className="grid-bg min-h-screen flex items-center justify-center">
        <p className="font-mono text-xs text-text-secondary animate-pulse">
          Checking license...
        </p>
      </div>
    );
  }

  // No email yet - first launch
  if (!license.email) {
    return <EmailPrompt onSubmit={license.setEmail} />;
  }

  // Error state (e.g. device mismatch, network error)
  if (license.error && !license.tier) {
    return (
      <div className="grid-bg min-h-screen flex items-center justify-center">
        <div className="border border-border bg-surface-raised p-[24px] max-w-md">
          <p className="font-mono text-xs text-red-400 uppercase tracking-wider mb-[12px]">
            License error
          </p>
          <p className="text-sm text-text-secondary mb-[24px]">
            {license.error}
          </p>
          <div className="flex items-center gap-4">
            <button
              onClick={license.refreshLicense}
              className="text-xs text-accent hover:underline"
            >
              Retry
            </button>
            <button
              onClick={license.clearEmail}
              className="text-xs text-text-secondary hover:underline"
            >
              Use different email
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Hit free limit and not licensed
  const hitLimit =
    license.status &&
    !license.status.licensed &&
    !license.tier &&
    license.status.generationsUsed >= license.status.generationsLimit;

  if (hitLimit) {
    return (
      <Paywall
        generationsUsed={license.status!.generationsUsed}
        generationsLimit={license.status!.generationsLimit}
        email={license.email}
        onSubscribe={() => license.requestCheckout(license.email!)}
        onRefresh={license.refreshLicense}
      />
    );
  }

  // Licensed (pro or free with remaining generations)
  return (
    <LicenseContext.Provider value={license}>{children}</LicenseContext.Provider>
  );
}
