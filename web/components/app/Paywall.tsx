"use client";

import Nav from "@/components/Nav";

interface Props {
  generationsUsed: number;
  generationsLimit: number;
  email: string;
  onSubscribe: () => void;
  onRefresh: () => void;
}

export default function Paywall({
  generationsUsed,
  generationsLimit,
  email,
  onSubscribe,
  onRefresh,
}: Props) {
  return (
    <div className="grid-bg min-h-screen">
      <Nav />
      <main className="mx-auto max-w-6xl px-6 py-[96px]">
        <div className="mb-[48px]">
          <h1 className="text-3xl font-bold tracking-tight">
            sche<span className="text-accent">MAGIC</span>
          </h1>
        </div>
        <div className="border border-border bg-surface-raised p-[24px] max-w-md">
          <p className="font-mono text-xs text-accent uppercase tracking-wider mb-[12px]">
            Free tier used
          </p>
          <p className="text-sm text-text-secondary mb-[24px]">
            You have used {generationsUsed} of {generationsLimit} free
            generations. Subscribe for $5 USD/month to keep generating symbols
            and footprints.
          </p>
          <button
            onClick={onSubscribe}
            className="bg-accent h-[48px] px-[24px] text-sm font-medium text-white rounded-lg hover:bg-accent-hover transition-colors w-full"
          >
            Subscribe - $5 USD/month
          </button>
          <div className="mt-[16px] flex items-center justify-between">
            <p className="text-xs text-text-secondary">
              Logged in as {email}
            </p>
            <button
              onClick={onRefresh}
              className="text-xs text-accent hover:underline"
            >
              Already subscribed? Refresh
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
