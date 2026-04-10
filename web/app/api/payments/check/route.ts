import { NextRequest, NextResponse } from "next/server";
import {
  getOrCreateCustomer,
  getFreeGenerations,
  FREE_GENERATION_LIMIT,
  getSubscriptionStatus,
} from "@/lib/stripe";

export async function GET(req: NextRequest) {
  const email = req.nextUrl.searchParams.get("email");
  if (!email) {
    return NextResponse.json({ error: "email required" }, { status: 400 });
  }

  const customer = await getOrCreateCustomer(email);
  const subscriptionStatus = await getSubscriptionStatus(customer.id);
  const licensed = subscriptionStatus === "active";
  const generationsUsed = getFreeGenerations(customer);

  return NextResponse.json({
    licensed,
    generationsUsed,
    generationsLimit: FREE_GENERATION_LIMIT,
    subscriptionStatus,
  });
}
