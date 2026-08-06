import type { PaymentProvider } from './provider';
import { stripeProvider } from './stripe';
import { abaPaywayProvider } from './aba-payway';
import { bakongProvider } from './bakong';

export * from './provider';

/**
 * Resolve the active payment provider from env (PAYMENT_PROVIDER).
 * Defaults to Stripe. Adding a real ABA/Bakong integration later means only
 * implementing that adapter — nothing in the checkout UI or API changes.
 */
export function getPaymentProvider(): PaymentProvider {
  const id = (process.env.PAYMENT_PROVIDER ?? 'stripe').toLowerCase();
  switch (id) {
    case 'aba':
      return abaPaywayProvider;
    case 'bakong':
      return bakongProvider;
    case 'stripe':
    default:
      return stripeProvider;
  }
}
