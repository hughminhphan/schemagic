import { NextRequest, NextResponse } from "next/server";
import { getStripe, getOrCreateCustomer, PRICE_ID, APP_URL } from "@/lib/stripe";
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
    const session = await getStripe().checkout.sessions.create({
      customer: customer.id,
      customer_email: undefined,
      mode: "subscription",
      line_items: [{ price: PRICE_ID, quantity: 1 }],
      success_url: `${APP_URL}/activate?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${APP_URL}/?checkout=canceled`,
    });
    return NextResponse.json({ url: session.url });
  } catch (err) {
    return stripeErrorResponse(err);
  }
}
