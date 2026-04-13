"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import type { LicenseStatus, ValidateResponse } from "@/lib/payments-types";
import type { LicenseContextValue, LicenseTier } from "@/components/app/LicenseContext";

const PAYMENTS_BASE = "https://www.schemagic.design/api/payments";
const LICENSE_BASE = "https://www.schemagic.design/api/license";
const AUTH_BASE = "https://www.schemagic.design/api/auth";
const LOCAL_KEY = "schemagic_license";
const IDENTITY_KEY = "schemagic_identity_token";

interface LicenseState {
  email: string | null;
  status: LicenseStatus | null;
  tier: LicenseTier;
  loading: boolean;
  error: string | null;
}

// --- Tauri bridge helpers ---

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

async function getTauriMachineId(): Promise<string | null> {
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    return await invoke<string>("get_machine_id");
  } catch {
    return null;
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

// --- Identity token helpers ---

interface IdentityPayload {
  email?: string;
  typ?: string;
  exp?: number;
}

function decodeIdentityToken(token: string): IdentityPayload | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const padded = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const json = atob(padded + "=".repeat((4 - (padded.length % 4)) % 4));
    const payload = JSON.parse(json) as IdentityPayload;
    if (payload.typ && payload.typ !== "identity") return null;
    if (payload.exp && payload.exp * 1000 < Date.now()) return null;
    return payload;
  } catch {
    return null;
  }
}

async function loadIdentityToken(): Promise<string | null> {
  const tauri = await readTauriConfig();
  const fromTauri = typeof tauri?.identity_token === "string" ? (tauri.identity_token as string) : "";
  if (fromTauri) return fromTauri;
  if (typeof localStorage !== "undefined") {
    return localStorage.getItem(IDENTITY_KEY);
  }
  return null;
}

async function storeIdentityToken(token: string): Promise<void> {
  await saveTauriConfig({ identity_token: token });
  try {
    localStorage.setItem(IDENTITY_KEY, token);
  } catch {
    // ignore
  }
}

async function clearIdentityToken(): Promise<void> {
  await saveTauriConfig({ identity_token: "", email: "" });
  try {
    localStorage.removeItem(IDENTITY_KEY);
  } catch {
    // ignore
  }
}

// --- Machine ID (browser fallback) ---

function getBrowserMachineId(): string {
  let id = localStorage.getItem("schemagic_machine_id");
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem("schemagic_machine_id", id);
  }
  return id;
}

// --- Main hook ---

export function useLicense(): LicenseContextValue {
  const [state, setState] = useState<LicenseState>({
    email: null,
    status: null,
    tier: null,
    loading: true,
    error: null,
  });

  const tokenRef = useRef<string | null>(null);
  const machineIdRef = useRef<string | null>(null);

  const validateWithServer = useCallback(
    async (email: string, machineId: string): Promise<ValidateResponse> => {
      const res = await fetch(`${LICENSE_BASE}/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, machine_id: machineId }),
      });
      return res.json();
    },
    []
  );

  const checkLicense = useCallback(
    async (email: string) => {
      setState((s) => ({ ...s, loading: true, email }));
      try {
        let machineId = await getTauriMachineId();
        if (!machineId) machineId = getBrowserMachineId();
        machineIdRef.current = machineId;

        const data = await validateWithServer(email, machineId);

        if (data.valid && data.token) {
          tokenRef.current = data.token;
          localStorage.setItem(
            LOCAL_KEY,
            JSON.stringify({ email, tier: data.tier, ts: Date.now() })
          );

          setState({
            email,
            status: {
              licensed: data.tier === "pro",
              generationsUsed: data.generationsUsed ?? 0,
              generationsLimit: data.generationsLimit ?? 3,
              subscriptionStatus: data.tier === "pro" ? "active" : "none",
            },
            tier: data.tier ?? null,
            loading: false,
            error: null,
          });
        } else {
          tokenRef.current = null;
          setState({
            email,
            status: {
              licensed: false,
              generationsUsed: data.generationsUsed ?? 0,
              generationsLimit: data.generationsLimit ?? 3,
              subscriptionStatus: "none",
            },
            tier: null,
            loading: false,
            error:
              data.reason === "device_mismatch"
                ? data.message ?? "This subscription is active on another device."
                : null,
          });
        }

        await saveTauriConfig({ email });
      } catch (err) {
        tokenRef.current = null;
        setState((s) => ({
          ...s,
          loading: false,
          error:
            err instanceof Error
              ? err.message
              : "License check failed. Check your internet connection.",
        }));
      }
    },
    [validateWithServer]
  );

  const applyIdentityToken = useCallback(
    async (token: string): Promise<boolean> => {
      const payload = decodeIdentityToken(token);
      if (!payload?.email) return false;
      await storeIdentityToken(token);
      await checkLicense(payload.email);
      return true;
    },
    [checkLicense]
  );

  // On mount: prefer identity_token; fall back to stored email (dev/transition only)
  useEffect(() => {
    (async () => {
      const storedToken = await loadIdentityToken();
      if (storedToken) {
        const payload = decodeIdentityToken(storedToken);
        if (payload?.email) {
          await checkLicense(payload.email);
          return;
        }
        // Expired or malformed — clear it
        await clearIdentityToken();
      }

      const tauriConfig = await readTauriConfig();
      const email =
        (tauriConfig?.email as string) ||
        (typeof localStorage !== "undefined" ? localStorage.getItem("schemagic_email") : null) ||
        null;

      if (!email) {
        setState({ email: null, status: null, tier: null, loading: false, error: null });
        return;
      }
      await checkLicense(email);
    })();
  }, [checkLicense]);

  // Listen for deep-link auth events from the Rust side
  useEffect(() => {
    let unlisten: (() => void) | null = null;
    (async () => {
      try {
        const { listen } = await import("@tauri-apps/api/event");
        unlisten = await listen<string>("deep-link-auth", async (event) => {
          const token = event.payload;
          if (typeof token === "string" && token.length > 0) {
            await applyIdentityToken(token);
          }
        });
      } catch {
        // Not in Tauri — deep links only work in the desktop shell
      }
    })();
    return () => {
      if (unlisten) unlisten();
    };
  }, [applyIdentityToken]);

  const requestMagicLink = useCallback(async (email: string) => {
    const res = await fetch(`${AUTH_BASE}/request`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    if (!res.ok) {
      const data = (await res.json().catch(() => ({}))) as { error?: string };
      throw new Error(data.error ?? "Failed to send magic link.");
    }
  }, []);

  const setEmail = useCallback(
    async (email: string) => {
      // Dev/legacy path: accept email without magic-link verification.
      // In production Tauri builds the UI should call requestMagicLink() instead.
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

  const acquireToken = useCallback(async (): Promise<string | null> => {
    if (state.tier === "pro" && tokenRef.current) {
      return tokenRef.current;
    }

    if (!state.email || !machineIdRef.current) return null;

    try {
      const data = await validateWithServer(state.email, machineIdRef.current);
      if (data.valid && data.token) {
        if (data.generationsUsed != null) {
          setState((s) =>
            s.status
              ? {
                  ...s,
                  status: {
                    ...s.status,
                    generationsUsed: data.generationsUsed!,
                  },
                  tier: data.tier ?? s.tier,
                }
              : s
          );
        }
        return data.token;
      }

      if (data.reason === "limit_reached") {
        setState((s) => ({
          ...s,
          status: s.status
            ? {
                ...s.status,
                generationsUsed: data.generationsUsed ?? s.status.generationsUsed,
              }
            : s.status,
          tier: null,
        }));
      }

      return null;
    } catch {
      return null;
    }
  }, [state.email, state.tier, validateWithServer]);

  const clearEmail = useCallback(() => {
    localStorage.removeItem("schemagic_email");
    localStorage.removeItem(LOCAL_KEY);
    tokenRef.current = null;
    void clearIdentityToken();
    setState({ email: null, status: null, tier: null, loading: false, error: null });
  }, []);

  return {
    ...state,
    setEmail,
    requestMagicLink,
    requestCheckout,
    requestPortal,
    refreshLicense,
    acquireToken,
    clearEmail,
  };
}
