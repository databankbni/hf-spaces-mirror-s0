/**
 * Payment provider abstraction. Checkout UI and API code depend ONLY on this
 * interface, so a local gateway (ABA PayWay / Bakong) can be dropped in later
 * by implementing one adapter — no changes to the checkout flow.
 */

export interface CreateCheckoutParams {
  orderId: string;
  templateName: string;
  tier: string;
  /** Amount in the smallest currency unit (e.g. cents). */
  amount: number;
  currency: string; // ISO 4217, e.g. "usd"
  successUrl: string;
  cancelUrl: string;
  customerEmail?: string;
}

export interface CheckoutResult {
  /** Where to redirect the buyer to complete payment. */
  redirectUrl: string;
  /** Provider-side reference (session id) stored on the order. */
  providerRef: string;
}

/** Normalised webhook outcome the app knows how to act on. */
export interface PaymentEvent {
  /** Stable, unique id for idempotency (e.g. Stripe event id). */
  eventId: string;
  type: 'payment_succeeded' | 'payment_failed' | 'ignored';
  orderId?: string;
  providerRef?: string;
}

export interface PaymentProvider {
  readonly id: 'stripe' | 'aba' | 'bakong';
  createCheckout(params: CreateCheckoutParams): Promise<CheckoutResult>;
  /** Verify signature + parse a raw webhook request into a normalised event. */
  parseWebhook(rawBody: string, signature: string | null): Promise<PaymentEvent>;
}

export class PaymentProviderNotConfigured extends Error {}
