import { NextResponse } from "next/server";
import Stripe from "stripe";

export function stripeErrorResponse(err: unknown): NextResponse {
  if (err instanceof Stripe.errors.StripeInvalidRequestError) {
    return NextResponse.json({ error: err.message }, { status: 400 });
  }
  if (err instanceof Stripe.errors.StripeError) {
    console.error("[stripe]", err.type, err.message);
    return NextResponse.json({ error: "Payment provider error" }, { status: 502 });
  }
  console.error("[route]", err);
  return NextResponse.json({ error: "Internal error" }, { status: 500 });
}
