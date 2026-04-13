import { NextRequest, NextResponse } from "next/server";
import { getStripe, getOrCreateCustomer, APP_URL } from "@/lib/stripe";
import { normalizeEmail } from "@/lib/email";
import { stripeErrorResponse } from "@/lib/api-helpers";

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

  try {
    const customer = await getOrCreateCustomer(email);
    const session = await getStripe().billingPortal.sessions.create({
      customer: customer.id,
      return_url: APP_URL,
    });
    return NextResponse.json({ url: session.url });
  } catch (err) {
    return stripeErrorResponse(err);
  }
}
