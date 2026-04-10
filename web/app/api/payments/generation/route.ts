import { NextRequest, NextResponse } from "next/server";
import {
  getOrCreateCustomer,
  getFreeGenerations,
  FREE_GENERATION_LIMIT,
  hasActiveSubscription,
  incrementFreeGenerations,
} from "@/lib/stripe";

export async function POST(req: NextRequest) {
  const { email } = await req.json();
  if (!email) {
    return NextResponse.json({ error: "email required" }, { status: 400 });
  }

  const customer = await getOrCreateCustomer(email);

  // Licensed users always allowed, don't increment free count
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
}
