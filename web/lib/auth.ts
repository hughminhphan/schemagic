import jwt from "jsonwebtoken";

export interface RequestTokenPayload {
  email: string;
  typ: "request";
  iat?: number;
  exp?: number;
}

export interface IdentityTokenPayload {
  email: string;
  typ: "identity";
  iat?: number;
  exp?: number;
}

const REQUEST_TTL_SECONDS = 60 * 15;
const IDENTITY_TTL_SECONDS = 60 * 60 * 24 * 30;

function secret(): string {
  const s = process.env.AUTH_SECRET;
  if (!s) throw new Error("AUTH_SECRET env var not set");
  return s;
}

export function signRequestToken(email: string): string {
  return jwt.sign({ email, typ: "request" }, secret(), {
    algorithm: "HS256",
    expiresIn: REQUEST_TTL_SECONDS,
  });
}

export function verifyRequestToken(token: string): RequestTokenPayload | null {
  try {
    const p = jwt.verify(token, secret(), { algorithms: ["HS256"] }) as RequestTokenPayload;
    if (p.typ !== "request") return null;
    return p;
  } catch {
    return null;
  }
}

export function signIdentityToken(email: string): string {
  return jwt.sign({ email, typ: "identity" }, secret(), {
    algorithm: "HS256",
    expiresIn: IDENTITY_TTL_SECONDS,
  });
}

export function verifyIdentityToken(token: string): IdentityTokenPayload | null {
  try {
    const p = jwt.verify(token, secret(), { algorithms: ["HS256"] }) as IdentityTokenPayload;
    if (p.typ !== "identity") return null;
    return p;
  } catch {
    return null;
  }
}
