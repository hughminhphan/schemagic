"use client";

import type { ReactNode } from "react";
import { WizardProvider } from "@/components/app/WizardProvider";

export default function WizardLayout({ children }: { children: ReactNode }) {
  return <WizardProvider>{children}</WizardProvider>;
}
