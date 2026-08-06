import {
  PaymentProviderNotConfigured,
  type CheckoutResult,
  type CreateCheckoutParams,
  type PaymentEvent,
  type PaymentProvider
} from './provider';

/**
 * Bakong (KHQR) adapter — STUB.
 *
 * TODO: Implement KHQR generation + Bakong transaction status polling:
 *   - generate a KHQR string/deeplink for the amount, render it on a pay page
 *   - poll Bakong's check-transaction API (or receive a callback) for success
 *   - map a confirmed transaction to a PaymentEvent in parseWebhook()/poller
 * Reads BAKONG_TOKEN from env.
 */
export const bakongProvider: PaymentProvider = {
  id: 'bakong',

  async createCheckout(_params: CreateCheckoutParams): Promise<CheckoutResult> {
    throw new PaymentProviderNotConfigured(
      'Bakong (KHQR) adapter is not implemented yet. Set PAYMENT_PROVIDER=stripe for now.'
    );
  },

  async parseWebhook(_rawBody: string, _signature: string | null): Promise<PaymentEvent> {
    throw new PaymentProviderNotConfigured('Bakong webhook parsing is not implemented yet.');
  }
};
