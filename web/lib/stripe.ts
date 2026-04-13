import Stripe from "stripe";
import { createHash } from "crypto";

function emailKey(email: string): string {
  return createHash("sha256").update(email).digest("hex").slice(0, 32);
}

let _stripe: Stripe | null = null;
export function getStripe(): Stripe {
  if (!_stripe) {
    // Force Node's http module instead of fetch: Next.js app router caches
    // fetch() responses by default, which pins stale customers.list results.
    _stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, {
      httpClient: Stripe.createNodeHttpClient(),
    });
  }
  return _stripe;
}

export const FREE_GENERATION_LIMIT = 3;
export const PRICE_ID = process.env.STRIPE_PRICE_ID!;
export const APP_URL = process.env.NEXT_PUBLIC_APP_URL || "https://schemagic.design";

/** Find or create a Stripe customer by normalized email.
 *
 * customers.list has seconds-to-minutes indexing delay, so a fresh signup
 * often returns empty even after the customer was created moments earlier.
 * When that happens we fall through to customers.create with an email-keyed
 * idempotency key — same email within Stripe's 24h window returns the
 * cached customer, so parallel signups on the same email dedup (Bug 5).
 *
 * If the cached customer was deleted externally (happens in the test
 * harness; rare in prod), retrieve will 404 and we retry without the key. */
export async function getOrCreateCustomer(email: string): Promise<Stripe.Customer> {
  const stripe = getStripe();
  const existing = await stripe.customers.list({ email, limit: 1 });
  if (existing.data.length > 0) return existing.data[0];
  const idempotencyKey = `create-customer:${emailKey(email)}`;
  const created = await stripe.customers.create(
    { email, metadata: { free_generations: "0" } },
    { idempotencyKey }
  );
  const verified = await stripe.customers.retrieve(created.id).catch(() => null);
  if (!verified || (verified as Stripe.DeletedCustomer).deleted) {
    return stripe.customers.create({ email, metadata: { free_generations: "0" } });
  }
  return created;
}

/** Read free generation count from customer metadata. */
export function getFreeGenerations(customer: Stripe.Customer): number {
  return parseInt(customer.metadata?.free_generations ?? "0", 10);
}

/** Pro tier statuses that grant access.
 * past_due keeps card-failed users licensed during the Stripe retry grace window. */
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
 * Idempotency key includes the target value so two requests that both read
 * the same "current" and try to set the same "next" coalesce on Stripe's
 * side (prevents retry double-writes). True parallel race hardening would
 * need a shared atomic counter (Redis); at $5/mo with a 3-gen cap, the
 * worst-case over-grant is acceptable. */
export async function incrementFreeGenerations(customer: Stripe.Customer): Promise<number> {
  const current = getFreeGenerations(customer);
  const next = current + 1;
  await getStripe().customers.update(
    customer.id,
    { metadata: { free_generations: String(next) } },
    { idempotencyKey: `inc-free:${customer.id}:${next}` }
  );
  return next;
}
