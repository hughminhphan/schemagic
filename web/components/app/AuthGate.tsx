"use client";

import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useLicense } from "@/hooks/useLicense";
import { LicenseContext } from "./LicenseContext";
import AppShell from "./AppShell";
import { TerminalLine } from "@/components/ui";

interface Props {
  /** `paid` routes require an active subscription OR free-tier credit. */
  mode?: "paid" | "authed";
  children: ReactNode;
}

function Splash({ label }: { label: string }) {
  return (
    <AppShell header="wordmarkOnly">
      <div className="flex-1 flex items-center justify-center">
        <TerminalLine>
          <span className="animate-pulse">{label}</span>
        </TerminalLine>
      </div>
    </AppShell>
  );
}

export default function AuthGate({ children, mode = "paid" }: Props) {
  const license = useLicense();
  const router = useRouter();

  const hitLimit =
    !!license.status &&
    !license.status.licensed &&
    !license.tier &&
    license.status.generationsUsed >= license.status.generationsLimit;

  useEffect(() => {
    if (license.loading) return;
    if (!license.email) {
      router.replace("/auth/email");
      return;
    }
    if (mode === "paid" && hitLimit) {
      router.replace("/auth/paywall");
    }
  }, [license.loading, license.email, hitLimit, mode, router]);

  if (license.loading) return <Splash label="Checking license..." />;
  if (!license.email) return <Splash label="Redirecting to sign in..." />;
  if (mode === "paid" && hitLimit) return <Splash label="Redirecting..." />;

  return (
    <LicenseContext.Provider value={license}>{children}</LicenseContext.Provider>
  );
}
