"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import type { LicenseStatus, ValidateResponse } from "@/lib/payments-types";
import type { LicenseContextValue, LicenseTier } from "@/components/app/LicenseContext";

const PAYMENTS_BASE = "https://schemagic.design/api/payments";
const LICENSE_BASE = "https://schemagic.design/api/license";
const LOCAL_KEY = "schemagic_license";

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

async function storeTauriLicenseToken(token: string): Promise<void> {
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("store_license_token", { token });
  } catch {
    // Not in Tauri
  }
}

async function getTauriLicenseToken(): Promise<string | null> {
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    const token = await invoke<string>("get_license_token");
    return token || null;
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

// --- JWT helpers (decode without verification, for expiry check only) ---

function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = JSON.parse(atob(parts[1].replace(/-/g, "+").replace(/_/g, "/")));
    return payload;
  } catch {
    return null;
  }
}

function isTokenExpiringSoon(token: string, bufferSeconds = 86400): boolean {
  const payload = decodeJwtPayload(token);
  if (!payload || typeof payload.exp !== "number") return true;
  return Date.now() / 1000 > payload.exp - bufferSeconds;
}

function isTokenExpired(token: string): boolean {
  return isTokenExpiringSoon(token, 0);
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
        // Get machine ID
        let machineId = await getTauriMachineId();
        if (!machineId) machineId = getBrowserMachineId();
        machineIdRef.current = machineId;

        // Check for cached token first
        let cachedToken = await getTauriLicenseToken();
        if (!cachedToken) cachedToken = localStorage.getItem("schemagic_token");

        // If we have a valid, non-expiring-soon pro token, use it without network call
        if (cachedToken && !isTokenExpiringSoon(cachedToken)) {
          const payload = decodeJwtPayload(cachedToken);
          if (payload?.tier === "pro") {
            tokenRef.current = cachedToken;
            setState({
              email,
              status: {
                licensed: true,
                generationsUsed: 0,
                generationsLimit: 3,
                subscriptionStatus: "active",
              },
              tier: "pro",
              loading: false,
              error: null,
            });
            return;
          }
        }

        // Call server to validate / get fresh token
        const data = await validateWithServer(email, machineId);

        if (data.valid && data.token) {
          tokenRef.current = data.token;
          // Persist token
          await storeTauriLicenseToken(data.token);
          localStorage.setItem("schemagic_token", data.token);
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
          // Not valid - show paywall or error
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

        // Persist email
        localStorage.setItem("schemagic_email", email);
        await saveTauriConfig({ email });
      } catch (err) {
        // Offline fallback: use cached token if still valid
        const cachedToken =
          (await getTauriLicenseToken()) ??
          localStorage.getItem("schemagic_token");
        if (cachedToken && !isTokenExpired(cachedToken)) {
          const payload = decodeJwtPayload(cachedToken);
          tokenRef.current = cachedToken;
          setState({
            email,
            status: {
              licensed: payload?.tier === "pro",
              generationsUsed: 0,
              generationsLimit: 3,
              subscriptionStatus:
                payload?.tier === "pro" ? "active" : "none",
            },
            tier: (payload?.tier as LicenseTier) ?? null,
            loading: false,
            error: null,
          });
          return;
        }

        // No cached token and offline - error state
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

  // On mount: read email from Tauri config or localStorage
  useEffect(() => {
    (async () => {
      const tauriConfig = await readTauriConfig();
      const email =
        (tauriConfig?.email as string) ||
        localStorage.getItem("schemagic_email") ||
        null;

      if (!email) {
        setState({ email: null, status: null, tier: null, loading: false, error: null });
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

  const acquireToken = useCallback(async (): Promise<string | null> => {
    // Pro users: return cached token (already validated on mount/refresh)
    if (state.tier === "pro" && tokenRef.current && !isTokenExpired(tokenRef.current)) {
      return tokenRef.current;
    }

    // Free tier: get a fresh single-use token from the server
    if (!state.email || !machineIdRef.current) return null;

    try {
      const data = await validateWithServer(state.email, machineIdRef.current);
      if (data.valid && data.token) {
        // Update generation count in state
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

      // Hit the limit
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
      // Network error - for free tier, we cannot fail open
      return null;
    }
  }, [state.email, state.tier, validateWithServer]);

  return {
    ...state,
    setEmail,
    requestCheckout,
    requestPortal,
    refreshLicense,
    acquireToken,
  };
}
