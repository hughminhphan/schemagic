import jwt from "jsonwebtoken";

const PRIVATE_KEY = process.env.LICENSE_PRIVATE_KEY!;

export interface LicenseTokenPayload {
  sub: string; // Stripe customer ID
  email: string;
  machine_id: string;
  tier: "pro" | "free";
  generation_id?: string; // For free tier single-use tokens
}

/** Sign a license JWT with RS256. */
export function signLicenseToken(
  payload: Omit<LicenseTokenPayload, "iat">,
  expiresInSeconds: number
): string {
  return jwt.sign(payload, PRIVATE_KEY, {
    algorithm: "RS256",
    expiresIn: expiresInSeconds,
  });
}

/** Verify a license JWT. Returns decoded payload or null. */
export function verifyLicenseToken(
  token: string
): LicenseTokenPayload | null {
  try {
    const PUBLIC_KEY = process.env.LICENSE_PUBLIC_KEY!;
    return jwt.verify(token, PUBLIC_KEY, {
      algorithms: ["RS256"],
    }) as LicenseTokenPayload;
  } catch {
    return null;
  }
}
