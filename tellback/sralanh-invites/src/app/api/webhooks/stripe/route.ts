import { NextResponse } from 'next/server';
import { getPaymentProvider } from '@/lib/payments';
import { createSupabaseAdminClient } from '@/lib/supabase/server';

// Must run on Node (needs the raw body + Stripe SDK crypto).
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(req: Request) {
  const rawBody = await req.text();
  const signature = req.headers.get('stripe-signature');
  const provider = getPaymentProvider();

  let event;
  try {
    event = await provider.parseWebhook(rawBody, signature);
  } catch (e) {
    // Signature mismatch / malformed -> tell the provider to stop retrying.
    return NextResponse.json(
      { error: e instanceof Error ? e.message : 'Invalid webhook' },
      { status: 400 }
    );
  }

  if (event.type === 'ignored') {
    return NextResponse.json({ received: true });
  }

  const admin = createSupabaseAdminClient();

  // --- Idempotency: the processed_webhook_events PK makes replays a no-op. ---
  const { error: dupErr } = await admin
    .from('processed_webhook_events')
    .insert({ event_id: event.eventId, provider: provider.id });

  if (dupErr) {
    // Unique violation => we've already handled this event. Ack with 200 so the
    // provider stops retrying, without double-fulfilling the order.
    if (dupErr.code === '23505') return NextResponse.json({ received: true, duplicate: true });
    return NextResponse.json({ error: 'DB error' }, { status: 500 });
  }

  if (event.orderId) {
    if (event.type === 'payment_succeeded') {
      await admin
        .from('orders')
        .update({ payment_status: 'paid' })
        .eq('id', event.orderId)
        .neq('payment_status', 'paid'); // guard against races
    } else if (event.type === 'payment_failed') {
      await admin.from('orders').update({ payment_status: 'failed' }).eq('id', event.orderId);
    }
  }

  return NextResponse.json({ received: true });
}
