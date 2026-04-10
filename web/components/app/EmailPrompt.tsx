"use client";

import { useState, type FormEvent } from "react";
import Nav from "@/components/Nav";
import { FREE_GENERATION_LIMIT } from "@/lib/payments-constants";

interface Props {
  onSubmit: (email: string) => void;
}

export default function EmailPrompt({ onSubmit }: Props) {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);

  async function handle(e: FormEvent) {
    e.preventDefault();
    const trimmed = email.trim().toLowerCase();
    if (!trimmed || !trimmed.includes("@")) return;
    setBusy(true);
    await onSubmit(trimmed);
    setBusy(false);
  }

  return (
    <div className="grid-bg min-h-screen">
      <Nav />
      <main className="mx-auto max-w-6xl px-6 py-[96px]">
        <div className="mb-[48px]">
          <h1 className="text-3xl font-bold tracking-tight">
            sche<span className="text-accent">MAGIC</span>
          </h1>
          <p className="mt-[12px] text-sm text-text-secondary">
            Enter your email to get started. You get{" "}
            {FREE_GENERATION_LIMIT} free generations.
          </p>
        </div>
        <form onSubmit={handle} className="flex flex-col gap-3 max-w-md">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            disabled={busy}
            className="w-full h-[48px] px-4 text-sm rounded-lg bg-surface-raised border border-border text-text-primary placeholder:text-text-secondary focus:outline-none focus:border-accent transition-colors"
            autoFocus
          />
          <button
            type="submit"
            disabled={busy || !email.trim()}
            className="bg-accent h-[48px] px-[24px] text-sm font-medium text-white rounded-lg hover:bg-accent-hover transition-colors disabled:opacity-40"
          >
            {busy ? "Checking..." : "Continue"}
          </button>
        </form>
      </main>
    </div>
  );
}
