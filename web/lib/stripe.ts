import Stripe from "stripe";

// Lazy-initialized to avoid crashing during static export builds
// where STRIPE_SECRET_KEY is not set.
let _stripe: Stripe | null = null;
export function getStripe(): Stripe {
  if (!_stripe) {
    _stripe = new Stripe(process.env.STRIPE_SECRET_KEY!);
  }
  return _stripe;
}

export const FREE_GENERATION_LIMIT = 3;
export const PRICE_ID = process.env.STRIPE_PRICE_ID!;
export const APP_URL = process.env.NEXT_PUBLIC_APP_URL || "https://schemagic.design";

/** Find or create a Stripe customer by email. */
export async function getOrCreateCustomer(email: string): Promise<Stripe.Customer> {
  const existing = await getStripe().customers.list({ email, limit: 1 });
  if (existing.data.length > 0) return existing.data[0];
  return getStripe().customers.create({ email, metadata: { free_generations: "0" } });
}

/** Read free generation count from customer metadata. */
export function getFreeGenerations(customer: Stripe.Customer): number {
  return parseInt(customer.metadata?.free_generations ?? "0", 10);
}

/** Check if customer has an active subscription. */
export async function hasActiveSubscription(customerId: string): Promise<boolean> {
  const subs = await getStripe().subscriptions.list({
    customer: customerId,
    status: "active",
    limit: 1,
  });
  return subs.data.length > 0;
}

/** Get subscription status string. */
export async function getSubscriptionStatus(
  customerId: string
): Promise<"active" | "none" | "canceled" | "past_due"> {
  const subs = await getStripe().subscriptions.list({
    customer: customerId,
    limit: 1,
  });
  if (subs.data.length === 0) return "none";
  const status = subs.data[0].status;
  if (status === "active") return "active";
  if (status === "canceled") return "canceled";
  if (status === "past_due") return "past_due";
  return "none";
}

/** Increment free generation count in customer metadata. */
export async function incrementFreeGenerations(customer: Stripe.Customer): Promise<number> {
  const current = getFreeGenerations(customer);
  const next = current + 1;
  await getStripe().customers.update(customer.id, {
    metadata: { free_generations: String(next) },
  });
  return next;
}
