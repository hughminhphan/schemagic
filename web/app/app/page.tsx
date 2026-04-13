"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import AppShell from "@/components/app/AppShell";
import { useLicense } from "@/hooks/useLicense";
import { TerminalLine } from "@/components/ui";

export default function BootPage() {
  const router = useRouter();
  const license = useLicense();

  useEffect(() => {
    if (license.loading) return;
    if (!license.email) {
      router.replace("/auth/email");
      return;
    }
    const hitLimit =
      !!license.status &&
      !license.status.licensed &&
      !license.tier &&
      license.status.generationsUsed >= license.status.generationsLimit;
    if (hitLimit) {
      router.replace("/auth/paywall");
      return;
    }
    router.replace("/wizard/idle");
  }, [license.loading, license.email, license.status, license.tier, router]);

  return (
    <AppShell header="wordmarkOnly">
      <div className="flex-1 flex items-center justify-center">
        <TerminalLine>
          <span className="animate-pulse">booting...</span>
        </TerminalLine>
      </div>
    </AppShell>
  );
}
