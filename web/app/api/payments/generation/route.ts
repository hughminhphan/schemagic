import { NextRequest, NextResponse } from "next/server";
import {
  getOrCreateCustomer,
  getFreeGenerations,
  FREE_GENERATION_LIMIT,
  hasActiveSubscription,
  incrementFreeGenerations,
} from "@/lib/stripe";
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

    if (await hasActiveSubscription(customer.id)) {
      return NextResponse.json({ allowed: true, licensed: true });
    }

    const used = getFreeGenerations(customer);
    if (used >= FREE_GENERATION_LIMIT) {
      return NextResponse.json({ allowed: false, licensed: false, generationsUsed: used });
    }

    const next = await incrementFreeGenerations(customer);
    return NextResponse.json({
      allowed: true,
      licensed: false,
      generationsUsed: next,
      generationsRemaining: FREE_GENERATION_LIMIT - next,
    });
  } catch (err) {
    return stripeErrorResponse(err);
  }
}
