/**
 * Returns the base URL for the scheMAGIC API.
 *
 * In Tauri desktop mode, the Rust shell injects window.__SCHEMAGIC_API_PORT__
 * after the sidecar starts. In web/dev mode, falls back to the Next.js proxy
 * (relative /api paths) or NEXT_PUBLIC_API_URL.
 */
export function apiBase(): string {
  const tauriPort = (window as unknown as Record<string, unknown>).__SCHEMAGIC_API_PORT__;
  if (typeof tauriPort === "number") {
    return `http://127.0.0.1:${tauriPort}`;
  }
  // Web mode: use env var or empty string (relative paths via Next.js rewrite proxy)
  return process.env.NEXT_PUBLIC_API_URL || "";
}
