"use client";

import { useRouter } from "next/navigation";
import type { ReactNode } from "react";

type Layout = "default" | "withBack" | "wordmarkOnly";

interface Props {
  layout?: Layout;
  backHref?: string;
  onBack?: () => void;
  right?: ReactNode;
}

function Wordmark() {
  return (
    <span className="font-sans text-h1 leading-none tracking-tight">
      <span className="text-text-primary">sch</span>
      <span className="text-accent">eMAGIC</span>
    </span>
  );
}

export default function Header({ layout = "default", backHref, onBack, right }: Props) {
  const router = useRouter();

  const handleBack = () => {
    if (onBack) return onBack();
    if (backHref) return router.push(backHref);
    router.back();
  };

  return (
    <header className="relative bg-surface-raised border-b-2 border-border px-12 py-5 flex items-center justify-center">
      {layout === "withBack" ? (
        <button
          type="button"
          onClick={handleBack}
          className="absolute left-12 font-sans text-body text-text-secondary hover:text-text-primary transition-colors"
        >
          ← Back
        </button>
      ) : null}

      <Wordmark />

      {layout === "default" && right ? (
        <div className="absolute right-12">{right}</div>
      ) : null}
      {layout === "default" && !right ? (
        <button
          type="button"
          onClick={() => router.push("/settings")}
          aria-label="Settings"
          className="absolute right-12 text-text-secondary hover:text-text-primary transition-colors"
        >
          <span className="font-sans text-body">⚙</span>
        </button>
      ) : null}
    </header>
  );
}
