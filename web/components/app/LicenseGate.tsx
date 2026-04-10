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

  // Hit free limit and not licensed
  const hitLimit =
    license.status &&
    !license.status.licensed &&
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

  // Provide license context to children (PartInput uses consumeGeneration)
  return (
    <LicenseContext.Provider value={license}>{children}</LicenseContext.Provider>
  );
}
