import {
  PaymentProviderNotConfigured,
  type CheckoutResult,
  type CreateCheckoutParams,
  type PaymentEvent,
  type PaymentProvider
} from './provider';

/**
 * ABA PayWay adapter — STUB.
 *
 * TODO: Implement using ABA PayWay's "purchase" API:
 *   - build the hashed request (merchant id + api key + tran_id + amount…)
 *   - POST to the PayWay checkout endpoint and redirect the buyer
 *   - verify the pushback/callback hash in parseWebhook()
 * Reads ABA_PAYWAY_MERCHANT_ID / ABA_PAYWAY_API_KEY from env.
 *
 * Kept behind the PaymentProvider interface so the checkout UI never changes.
 */
export const abaPaywayProvider: PaymentProvider = {
  id: 'aba',

  async createCheckout(_params: CreateCheckoutParams): Promise<CheckoutResult> {
    throw new PaymentProviderNotConfigured(
      'ABA PayWay adapter is not implemented yet. Set PAYMENT_PROVIDER=stripe for now.'
    );
  },

  async parseWebhook(_rawBody: string, _signature: string | null): Promise<PaymentEvent> {
    throw new PaymentProviderNotConfigured('ABA PayWay webhook parsing is not implemented yet.');
  }
};
