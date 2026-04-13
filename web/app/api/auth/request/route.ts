import { NextRequest, NextResponse } from "next/server";
import { Resend } from "resend";
import { signRequestToken } from "@/lib/auth";
import { normalizeEmail } from "@/lib/email";

const VERIFY_BASE_URL =
  process.env.AUTH_VERIFY_BASE_URL ?? "https://www.schemagic.design";
const FROM_ADDRESS =
  process.env.AUTH_FROM_ADDRESS ?? "scheMAGIC <auth@schemagic.design>";

export async function POST(req: NextRequest) {
  let body: { email?: unknown };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const email = normalizeEmail(body.email);
  if (!email) {
    return NextResponse.json({ error: "Invalid email" }, { status: 400 });
  }

  const resendKey = process.env.RESEND_API_KEY;
  if (!resendKey) {
    return NextResponse.json(
      { error: "Auth not configured" },
      { status: 500 }
    );
  }

  const token = signRequestToken(email);
  const verifyUrl = `${VERIFY_BASE_URL}/auth/verify?token=${encodeURIComponent(
    token
  )}`;

  try {
    const resend = new Resend(resendKey);
    const { error } = await resend.emails.send({
      from: FROM_ADDRESS,
      to: email,
      subject: "Sign in to scheMAGIC",
      text: `Click to sign in to scheMAGIC:\n\n${verifyUrl}\n\nThis link expires in 15 minutes. If you didn't request it, ignore this email.`,
      html: renderEmail(verifyUrl),
    });
    if (error) {
      return NextResponse.json(
        { error: "Failed to send email" },
        { status: 502 }
      );
    }
  } catch {
    return NextResponse.json({ error: "Failed to send email" }, { status: 502 });
  }

  return NextResponse.json({ ok: true });
}

function renderEmail(url: string): string {
  return `<!doctype html>
<html>
<body style="font-family: -apple-system, system-ui, sans-serif; background: #0A0A0A; color: #fff; padding: 48px 24px;">
  <div style="max-width: 480px; margin: 0 auto; background: #111; border: 1px solid #1A1A1A; border-radius: 8px; padding: 32px;">
    <h1 style="font-size: 24px; margin: 0 0 16px;">Sign in to scheMAGIC</h1>
    <p style="color: #888; line-height: 1.5;">Click the button below to sign in. This link expires in 15 minutes.</p>
    <p style="margin: 32px 0;">
      <a href="${url}" style="display: inline-block; background: #FF2D78; color: #fff; text-decoration: none; padding: 12px 24px; border-radius: 6px; font-weight: 600;">Sign in</a>
    </p>
    <p style="color: #888; font-size: 12px; word-break: break-all;">Or paste this URL into your browser:<br>${url}</p>
  </div>
</body>
</html>`;
}
