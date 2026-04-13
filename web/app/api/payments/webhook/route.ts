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

  const stripe = getStripe();

  try {
    switch (event.type) {
      case "customer.subscription.deleted": {
        const sub = event.data.object as { customer: string };
        await stripe.customers.update(sub.customer as string, {
          metadata: { machine_id: "" },
        });
        break;
      }
      case "invoice.payment_failed": {
        const invoice = event.data.object as { customer: string };
        await stripe.customers.update(invoice.customer as string, {
          metadata: { payment_failed: "true" },
        });
        break;
      }
      case "invoice.payment_succeeded": {
        // Stripe metadata merges key-by-key; empty string deletes the key.
        const invoice = event.data.object as { customer: string };
        await stripe.customers.update(invoice.customer as string, {
          metadata: { payment_failed: "" },
        });
        break;
      }
      case "customer.subscription.updated":
        break;
    }
  } catch (err) {
    // Swallow handler errors: returning non-2xx makes Stripe retry for 3 days,
    // which floods logs and re-fires idempotent side effects. All handled event
    // types are themselves idempotent (set-flag / clear-flag writes), so safe
    // to drop on the floor after logging.
    console.error("[webhook]", event.type, event.id, err);
  }

  return NextResponse.json({ received: true });
}
