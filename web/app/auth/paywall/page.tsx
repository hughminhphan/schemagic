"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import AppShell from "@/components/app/AppShell";
import { useLicense } from "@/hooks/useLicense";
import { Badge, Button, Card, CardRow, TerminalLine } from "@/components/ui";

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

  const used = license.status?.generationsUsed ?? 0;
  const limit = license.status?.generationsLimit ?? 3;

  return (
    <AppShell header="withBack" backHref="/wizard/idle">
      <div className="flex-1 flex items-center justify-center px-12 py-24">
        <div className="w-full max-w-2xl flex flex-col gap-12">
          <div className="flex flex-col gap-6">
            <TerminalLine>auth/paywall</TerminalLine>
            <h1 className="font-sans text-h1 text-text-primary">
              Free tier reached
            </h1>
            <p className="font-sans text-body text-text-secondary">
              You&apos;ve used {used} of {limit} free generations. Upgrade for
              unlimited symbols.
            </p>
          </div>

          <Card header={<span>Pro &middot; $5 USD / month</span>}>
            <CardRow label="Unlimited generations" value={<Badge variant="pro">Pro</Badge>} />
            <CardRow label="All manufacturers" value="Included" />
            <CardRow label="Priority datasheet fetch" value="Included" />
            <CardRow label="Cancel anytime" value="Stripe" />
          </Card>

          <div className="flex items-center gap-6">
            <Button onClick={handleSubscribe}>Upgrade</Button>
            <Button
              variant="secondary"
              onClick={() => license.refreshLicense()}
            >
              I&apos;ve already paid
            </Button>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
