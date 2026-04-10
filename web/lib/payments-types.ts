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
