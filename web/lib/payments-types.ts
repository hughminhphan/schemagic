export interface LicenseStatus {
  licensed: boolean;
  generationsUsed: number;
  generationsLimit: number;
  subscriptionStatus: "active" | "none" | "canceled" | "past_due";
}

export interface GenerationPermission {
  allowed: boolean;
  licensed: boolean;
  generationsUsed?: number;
  generationsRemaining?: number;
}

/** Response from /api/license/validate */
export interface ValidateResponse {
  valid: boolean;
  token?: string;
  tier?: "pro" | "free";
  reason?: "no_account" | "device_mismatch" | "limit_reached";
  message?: string;
  generationsUsed?: number;
  generationsLimit?: number;
  generationsRemaining?: number;
}
