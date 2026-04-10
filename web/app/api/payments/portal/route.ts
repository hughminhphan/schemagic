import { NextRequest, NextResponse } from "next/server";
import { getStripe, getOrCreateCustomer, APP_URL } from "@/lib/stripe";

export async function POST(req: NextRequest) {
  const { email } = await req.json();
  if (!email) {
    return NextResponse.json({ error: "email required" }, { status: 400 });
  }

  const customer = await getOrCreateCustomer(email);

  const session = await getStripe().billingPortal.sessions.create({
    customer: customer.id,
    return_url: APP_URL,
  });

  return NextResponse.json({ url: session.url });
}
