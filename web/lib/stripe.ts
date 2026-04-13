import Stripe from "stripe";

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

/** Find or create a Stripe customer by normalized email.
 * Caller must normalize email via normalizeEmail() before passing in.
 * Idempotency key on create() dedupes parallel signups within Stripe's 24h window. */
export async function getOrCreateCustomer(email: string): Promise<Stripe.Customer> {
  const existing = await getStripe().customers.list({ email, limit: 1 });
  if (existing.data.length > 0) return existing.data[0];
  return getStripe().customers.create(
    { email, metadata: { free_generations: "0" } },
    { idempotencyKey: `create-customer:${email}` }
  );
}

/** Read free generation count from customer metadata. */
export function getFreeGenerations(customer: Stripe.Customer): number {
  return parseInt(customer.metadata?.free_generations ?? "0", 10);
}

/** Pro tier statuses that grant access.
 * past_due keeps card-failed users licensed during the Stripe retry grace window
 * (the validate endpoint separately shortens their JWT via payment_failed flag). */
const PRO_STATUSES: readonly Stripe.Subscription.Status[] = [
  "active",
  "trialing",
  "past_due",
];

export async function hasActiveSubscription(customerId: string): Promise<boolean> {
  const subs = await getStripe().subscriptions.list({
    customer: customerId,
    limit: 5,
  });
  return subs.data.some((s) => PRO_STATUSES.includes(s.status));
}

export async function getSubscriptionStatus(
  customerId: string
): Promise<"active" | "trialing" | "past_due" | "canceled" | "none"> {
  const subs = await getStripe().subscriptions.list({ customer: customerId, limit: 1 });
  if (subs.data.length === 0) return "none";
  const status = subs.data[0].status;
  if (status === "active" || status === "trialing" || status === "past_due" || status === "canceled") {
    return status;
  }
  return "none";
}

/** Increment free generation count.
 * Idempotency key includes a 2s time bucket to coalesce duplicate rapid-fire
 * requests (e.g. double-click retries) into a single Stripe write. True parallel
 * race hardening would need a shared atomic counter (Redis); at $5/mo with a
 * 3-gen cap, the worst-case over-grant is acceptable. */
export async function incrementFreeGenerations(customer: Stripe.Customer): Promise<number> {
  const current = getFreeGenerations(customer);
  const next = current + 1;
  const bucket = Math.floor(Date.now() / 2000);
  await getStripe().customers.update(
    customer.id,
    { metadata: { free_generations: String(next) } },
    { idempotencyKey: `inc-free:${customer.id}:${bucket}` }
  );
  return next;
}
