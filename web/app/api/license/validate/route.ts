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
import { normalizeEmail } from "@/lib/email";
import { stripeErrorResponse } from "@/lib/api-helpers";

export async function POST(req: NextRequest) {
  let body: { email?: unknown; machine_id?: unknown };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const email = normalizeEmail(body.email);
  if (!email) {
    return NextResponse.json({ error: "Invalid email" }, { status: 400 });
  }
  const machine_id =
    typeof body.machine_id === "string" ? body.machine_id.trim() : "";
  if (!machine_id) {
    return NextResponse.json({ error: "machine_id required" }, { status: 400 });
  }

  try {
    const customer = await getOrCreateCustomer(email);

    if (await hasActiveSubscription(customer.id)) {
      const storedMachineId = customer.metadata?.machine_id;

      if (!storedMachineId) {
        await getStripe().customers.update(customer.id, {
          metadata: { machine_id },
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

      const token = signLicenseToken(
        { sub: customer.id, email, machine_id, tier: "pro" },
        3600
      );

      return NextResponse.json({ valid: true, token, tier: "pro" });
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

    const next = await incrementFreeGenerations(customer);

    const token = signLicenseToken(
      {
        sub: customer.id,
        email,
        machine_id,
        tier: "free",
        generation_id: randomUUID(),
      },
      300
    );

    return NextResponse.json({
      valid: true,
      token,
      tier: "free",
      generationsUsed: next,
      generationsLimit: FREE_GENERATION_LIMIT,
      generationsRemaining: FREE_GENERATION_LIMIT - next,
    });
  } catch (err) {
    return stripeErrorResponse(err);
  }
}
