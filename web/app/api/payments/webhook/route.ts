import { NextRequest, NextResponse } from "next/server";
import { getStripe } from "@/lib/stripe";

export async function POST(req: NextRequest) {
  const body = await req.text();
  const sig = req.headers.get("stripe-signature");

  if (!sig) {
    return NextResponse.json({ error: "No signature" }, { status: 400 });
  }

  let event;
  try {
    event = getStripe().webhooks.constructEvent(
      body,
      sig,
      process.env.STRIPE_WEBHOOK_SECRET!
    );
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: `Webhook error: ${message}` }, { status: 400 });
  }

  // License status is checked live from Stripe on each app launch,
  // so there is no local state to invalidate. The webhook exists for
  // Stripe compliance and future extension (e.g. analytics, email notifications).
  switch (event.type) {
    case "customer.subscription.deleted":
    case "customer.subscription.updated":
    case "invoice.payment_failed":
      // No-op for now. The /check endpoint always reads live Stripe state.
      break;
  }

  return NextResponse.json({ received: true });
}
