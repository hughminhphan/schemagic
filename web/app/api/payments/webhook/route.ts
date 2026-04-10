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

  switch (event.type) {
    case "customer.subscription.deleted": {
      // Clear machine_id so user can reactivate on a new device if they resubscribe
      const sub = event.data.object as { customer: string };
      await stripe.customers.update(sub.customer as string, {
        metadata: { machine_id: "" },
      });
      break;
    }
    case "invoice.payment_failed": {
      // Flag the customer so the validate endpoint shortens JWT expiry
      const invoice = event.data.object as { customer: string };
      const customer = await stripe.customers.retrieve(invoice.customer as string);
      if (!customer.deleted) {
        await stripe.customers.update(invoice.customer as string, {
          metadata: { ...customer.metadata, payment_failed: "true" },
        });
      }
      break;
    }
    case "invoice.payment_succeeded": {
      // Clear payment_failed flag on successful payment
      const invoice = event.data.object as { customer: string };
      const customer = await stripe.customers.retrieve(invoice.customer as string);
      if (!customer.deleted) {
        const meta = { ...customer.metadata };
        delete meta.payment_failed;
        await stripe.customers.update(invoice.customer as string, {
          metadata: meta,
        });
      }
      break;
    }
    case "customer.subscription.updated":
      // Log only for now
      break;
  }

  return NextResponse.json({ received: true });
}
