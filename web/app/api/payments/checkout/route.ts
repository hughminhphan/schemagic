import { NextRequest, NextResponse } from "next/server";
import { getStripe, getOrCreateCustomer, PRICE_ID, APP_URL } from "@/lib/stripe";

export async function POST(req: NextRequest) {
  const { email } = await req.json();
  if (!email) {
    return NextResponse.json({ error: "email required" }, { status: 400 });
  }

  const customer = await getOrCreateCustomer(email);

  const session = await getStripe().checkout.sessions.create({
    customer: customer.id,
    mode: "subscription",
    line_items: [{ price: PRICE_ID, quantity: 1 }],
    success_url: `${APP_URL}/?checkout=success`,
    cancel_url: `${APP_URL}/?checkout=canceled`,
  });

  return NextResponse.json({ url: session.url });
}
