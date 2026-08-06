import Stripe from 'stripe';
import type {
  CheckoutResult,
  CreateCheckoutParams,
  PaymentEvent,
  PaymentProvider
} from './provider';

function getStripe(): Stripe {
  const key = process.env.STRIPE_SECRET_KEY;
  if (!key) throw new Error('STRIPE_SECRET_KEY is not set');
  return new Stripe(key, { apiVersion: '2024-06-20' });
}

export const stripeProvider: PaymentProvider = {
  id: 'stripe',

  async createCheckout(params: CreateCheckoutParams): Promise<CheckoutResult> {
    const stripe = getStripe();
    const session = await stripe.checkout.sessions.create({
      mode: 'payment',
      customer_email: params.customerEmail,
      line_items: [
        {
          quantity: 1,
          price_data: {
            currency: params.currency,
            unit_amount: params.amount,
            product_data: {
              name: `${params.templateName} — ${params.tier}`
            }
          }
        }
      ],
      // orderId travels with the session so the webhook can fulfil it
      // idempotently without trusting anything from the browser.
      metadata: { orderId: params.orderId },
      success_url: params.successUrl,
      cancel_url: params.cancelUrl
    });

    return {
      redirectUrl: session.url ?? params.cancelUrl,
      providerRef: session.id
    };
  },

  async parseWebhook(rawBody: string, signature: string | null): Promise<PaymentEvent> {
    const stripe = getStripe();
    const secret = process.env.STRIPE_WEBHOOK_SECRET;
    if (!secret) throw new Error('STRIPE_WEBHOOK_SECRET is not set');
    if (!signature) throw new Error('Missing stripe-signature header');

    // Throws on signature mismatch -> route returns 400.
    const event = stripe.webhooks.constructEvent(rawBody, signature, secret);

    switch (event.type) {
      case 'checkout.session.completed': {
        const session = event.data.object as Stripe.Checkout.Session;
        return {
          eventId: event.id,
          type: session.payment_status === 'paid' ? 'payment_succeeded' : 'ignored',
          orderId: session.metadata?.orderId,
          providerRef: session.id
        };
      }
      case 'checkout.session.async_payment_failed':
      case 'payment_intent.payment_failed': {
        const obj = event.data.object as { metadata?: { orderId?: string } };
        return { eventId: event.id, type: 'payment_failed', orderId: obj.metadata?.orderId };
      }
      default:
        return { eventId: event.id, type: 'ignored' };
    }
  }
};
