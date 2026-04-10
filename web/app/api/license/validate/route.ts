import { NextRequest, NextResponse } from "next/server";
import { randomUUID } from "crypto";
import {
  getOrCreateCustomer,
  getFreeGenerations,
  hasActiveSubscription,
  incrementFreeGenerations,
  FREE_GENERATION_LIMIT,
  getStripe,
} from "@/lib/stripe";
import { signLicenseToken } from "@/lib/license";

export async function POST(req: NextRequest) {
  let body: { email?: string; machine_id?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const { email, machine_id } = body;
  if (!email) {
    return NextResponse.json({ error: "email required" }, { status: 400 });
  }
  if (!machine_id) {
    return NextResponse.json(
      { error: "machine_id required" },
      { status: 400 }
    );
  }

  const customer = await getOrCreateCustomer(email);

  // --- Pro tier: active subscription ---
  if (await hasActiveSubscription(customer.id)) {
    const storedMachineId = customer.metadata?.machine_id;

    // First activation: bind this machine
    if (!storedMachineId) {
      await getStripe().customers.update(customer.id, {
        metadata: { ...customer.metadata, machine_id },
      });
    } else if (storedMachineId !== machine_id) {
      return NextResponse.json(
        {
          valid: false,
          reason: "device_mismatch",
          message:
            "This subscription is active on another device. Contact support to transfer.",
        },
        { status: 403 }
      );
    }

    // Check if payment recently failed (shorten expiry)
    const paymentFailed = customer.metadata?.payment_failed === "true";
    const expiresInSeconds = paymentFailed ? 3 * 86400 : 7 * 86400; // 3d or 7d

    const token = signLicenseToken(
      {
        sub: customer.id,
        email,
        machine_id,
        tier: "pro",
      },
      expiresInSeconds
    );

    return NextResponse.json({
      valid: true,
      token,
      tier: "pro",
    });
  }

  // --- Free tier ---
  const used = getFreeGenerations(customer);
  if (used >= FREE_GENERATION_LIMIT) {
    return NextResponse.json({
      valid: false,
      reason: "limit_reached",
      generationsUsed: used,
      generationsLimit: FREE_GENERATION_LIMIT,
    });
  }

  // Increment generation count and issue a single-use short-lived token
  const next = await incrementFreeGenerations(customer);

  const token = signLicenseToken(
    {
      sub: customer.id,
      email,
      machine_id,
      tier: "free",
      generation_id: randomUUID(),
    },
    300 // 5 minutes
  );

  return NextResponse.json({
    valid: true,
    token,
    tier: "free",
    generationsUsed: next,
    generationsLimit: FREE_GENERATION_LIMIT,
    generationsRemaining: FREE_GENERATION_LIMIT - next,
  });
}
