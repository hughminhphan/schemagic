"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import AppShell from "@/components/app/AppShell";
import { useLicense } from "@/hooks/useLicense";
import { Button } from "@/components/ui";

export default function AuthPaywallPage() {
  const router = useRouter();
  const license = useLicense();

  useEffect(() => {
    if (license.loading) return;
    if (!license.email) {
      router.replace("/auth/email");
      return;
    }
    if (license.tier === "pro") {
      router.replace("/wizard/idle");
    }
  }, [license.loading, license.email, license.tier, router]);

  const handleSubscribe = async () => {
    if (!license.email) return;
    await license.requestCheckout(license.email);
  };

  const used = license.status?.generationsUsed ?? 3;
  const limit = license.status?.generationsLimit ?? 3;

  return (
    <AppShell header="withBack" backHref="/wizard/idle">
      <div className="flex-1 flex items-center justify-center px-12 py-24">
        <div className="w-full max-w-2xl">
          <div className="flex flex-col gap-8 bg-surface-raised border-2 border-border p-12">
            <p className="font-sans text-mono-label uppercase tracking-wide text-accent">
              Free tier used
            </p>
            <p className="font-sans text-body text-text-secondary">
              You have used {used} of {limit} free generations. Subscribe for
              $5 USD/month to keep generating symbols and footprints.
            </p>
            <div>
              <Button onClick={handleSubscribe}>Subscribe — $5 USD/month</Button>
            </div>
            <button
              type="button"
              onClick={() => license.refreshLicense()}
              className="self-start font-sans text-body text-accent hover:text-accent-hover"
            >
              Already subscribed? Refresh
            </button>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
