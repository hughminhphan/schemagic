"use client";

import { useState, useEffect, useCallback } from "react";
import type { LicenseStatus } from "@/lib/payments-types";
import type { LicenseContextValue } from "@/components/app/LicenseContext";

const PAYMENTS_BASE = "https://schemagic.design/api/payments";
const LOCAL_KEY = "schemagic_license";

interface LicenseState {
  email: string | null;
  status: LicenseStatus | null;
  loading: boolean;
  error: string | null;
}

async function readTauriConfig(): Promise<Record<string, unknown> | null> {
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    return await invoke<Record<string, unknown>>("read_config");
  } catch {
    return null;
  }
}

async function saveTauriConfig(patch: Record<string, unknown>): Promise<void> {
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    const config = await invoke<Record<string, unknown>>("read_config");
    await invoke("save_config_cmd", { config: { ...config, ...patch } });
  } catch {
    // Not in Tauri
  }
}

async function openExternal(url: string): Promise<void> {
  try {
    const { open } = await import("@tauri-apps/plugin-shell");
    await open(url);
  } catch {
    window.open(url, "_blank");
  }
}

export function useLicense(): LicenseContextValue {
  const [state, setState] = useState<LicenseState>({
    email: null,
    status: null,
    loading: true,
    error: null,
  });

  const checkLicense = useCallback(async (email: string) => {
    setState((s) => ({ ...s, loading: true, email }));
    try {
      const res = await fetch(
        `${PAYMENTS_BASE}/check?email=${encodeURIComponent(email)}`
      );
      if (!res.ok) throw new Error(`Check failed: ${res.status}`);
      const status: LicenseStatus = await res.json();
      setState({ email, status, loading: false, error: null });

      // Cache for offline resilience
      localStorage.setItem(
        LOCAL_KEY,
        JSON.stringify({ email, status, ts: Date.now() })
      );

      // Persist email to Tauri config
      saveTauriConfig({ email });
    } catch (err) {
      // Fall back to localStorage cache (valid 24h)
      const cached = localStorage.getItem(LOCAL_KEY);
      if (cached) {
        const parsed = JSON.parse(cached);
        if (Date.now() - parsed.ts < 24 * 60 * 60 * 1000) {
          setState({
            email: parsed.email,
            status: parsed.status,
            loading: false,
            error: null,
          });
          return;
        }
      }
      setState((s) => ({
        ...s,
        loading: false,
        error: err instanceof Error ? err.message : "License check failed",
      }));
    }
  }, []);

  // On mount: read email from Tauri config or localStorage
  useEffect(() => {
    (async () => {
      const tauriConfig = await readTauriConfig();
      const email =
        (tauriConfig?.email as string) ||
        localStorage.getItem("schemagic_email") ||
        null;

      if (!email) {
        setState({ email: null, status: null, loading: false, error: null });
        return;
      }
      await checkLicense(email);
    })();
  }, [checkLicense]);

  const setEmail = useCallback(
    async (email: string) => {
      localStorage.setItem("schemagic_email", email);
      await saveTauriConfig({ email });
      await checkLicense(email);
    },
    [checkLicense]
  );

  const refreshLicense = useCallback(async () => {
    if (state.email) await checkLicense(state.email);
  }, [state.email, checkLicense]);

  const requestCheckout = useCallback(async (email: string) => {
    const res = await fetch(`${PAYMENTS_BASE}/checkout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    const { url } = await res.json();
    await openExternal(url);
  }, []);

  const requestPortal = useCallback(async () => {
    if (!state.email) return;
    const res = await fetch(`${PAYMENTS_BASE}/portal`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: state.email }),
    });
    const { url } = await res.json();
    await openExternal(url);
  }, [state.email]);

  const consumeGeneration = useCallback(async (): Promise<boolean> => {
    if (!state.email) return false;
    const res = await fetch(`${PAYMENTS_BASE}/generation`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: state.email }),
    });
    const data = await res.json();
    if (data.allowed && data.generationsUsed != null) {
      setState((s) =>
        s.status
          ? {
              ...s,
              status: { ...s.status, generationsUsed: data.generationsUsed },
            }
          : s
      );
    }
    return data.allowed;
  }, [state.email]);

  return {
    ...state,
    setEmail,
    requestCheckout,
    requestPortal,
    consumeGeneration,
    refreshLicense,
  };
}
