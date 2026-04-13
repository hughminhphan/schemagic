"use client";

import AppShell from "@/components/app/AppShell";
import AuthGate from "@/components/app/AuthGate";
import { useLicenseContext } from "@/components/app/LicenseContext";
import {
  Badge,
  Button,
  Card,
  CardRow,
  Tabs,
  TabsList,
  TabsPanel,
  TabsTrigger,
} from "@/components/ui";

function Settings() {
  const license = useLicenseContext();

  return (
    <AppShell header="withBack" backHref="/wizard/idle">
      <div className="flex-1 px-12 py-24">
        <div className="mx-auto max-w-3xl flex flex-col gap-12">
          <h1 className="font-sans text-h1 text-text-primary">
            Settings
          </h1>

          <Tabs defaultValue="account">
            <TabsList>
              <TabsTrigger value="account">Account</TabsTrigger>
              <TabsTrigger value="billing">Billing</TabsTrigger>
              <TabsTrigger value="preferences">Preferences</TabsTrigger>
            </TabsList>

            <TabsPanel value="account">
              <Card header={<span>Account</span>}>
                <CardRow label="Email" value={license.email ?? "—"} />
                <CardRow
                  label="Tier"
                  value={
                    license.tier === "pro" ? (
                      <Badge variant="pro">Pro</Badge>
                    ) : (
                      <Badge variant="free">Free</Badge>
                    )
                  }
                />
                <CardRow
                  label="Sign out"
                  value={
                    <Button variant="secondary" onClick={license.clearEmail}>
                      Sign out
                    </Button>
                  }
                />
              </Card>
            </TabsPanel>

            <TabsPanel value="billing">
              <Card header={<span>Billing</span>}>
                <CardRow
                  label="Subscription"
                  value={
                    license.tier === "pro" ? (
                      <Badge variant="success">Active</Badge>
                    ) : (
                      <Badge variant="free">None</Badge>
                    )
                  }
                />
                <CardRow
                  label="Manage subscription"
                  value={
                    <Button
                      variant="secondary"
                      onClick={() => license.requestPortal()}
                      disabled={license.tier !== "pro"}
                    >
                      Open Stripe portal
                    </Button>
                  }
                />
              </Card>
            </TabsPanel>

            <TabsPanel value="preferences">
              <Card header={<span>Preferences</span>}>
                <CardRow label="KiCad project path" value="Coming soon" />
                <CardRow label="Launch on login" value="Coming soon" />
                <CardRow label="Global hotkey" value="Coming soon" />
              </Card>
            </TabsPanel>
          </Tabs>
        </div>
      </div>
    </AppShell>
  );
}

export default function SettingsPage() {
  return (
    <AuthGate mode="authed">
      <Settings />
    </AuthGate>
  );
}
