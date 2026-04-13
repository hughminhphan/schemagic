import { NextRequest, NextResponse } from "next/server";
import {
  getOrCreateCustomer,
  getFreeGenerations,
  FREE_GENERATION_LIMIT,
  getSubscriptionStatus,
} from "@/lib/stripe";
import { normalizeEmail } from "@/lib/email";
import { stripeErrorResponse } from "@/lib/api-helpers";

export async function GET(req: NextRequest) {
  const email = normalizeEmail(req.nextUrl.searchParams.get("email"));
  if (!email) {
    return NextResponse.json({ error: "Invalid email" }, { status: 400 });
  }

  try {
    const customer = await getOrCreateCustomer(email);
    const subscriptionStatus = await getSubscriptionStatus(customer.id);
    const licensed =
      subscriptionStatus === "active" ||
      subscriptionStatus === "trialing" ||
      subscriptionStatus === "past_due";
    const generationsUsed = getFreeGenerations(customer);

    return NextResponse.json({
      licensed,
      generationsUsed,
      generationsLimit: FREE_GENERATION_LIMIT,
      subscriptionStatus,
    });
  } catch (err) {
    return stripeErrorResponse(err);
  }
}
