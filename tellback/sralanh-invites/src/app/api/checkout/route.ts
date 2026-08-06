import { NextResponse } from 'next/server';
import { z } from 'zod';
import { getTemplate, priceFor, type Tier } from '@/data/templates';
import { emptyInvite } from '@/data/mock-invite';
import { createSupabaseServerClient, createSupabaseAdminClient } from '@/lib/supabase/server';
import { getPaymentProvider } from '@/lib/payments';
import { coupleSlug, ensureUniqueSlug } from '@/lib/slug';

export const runtime = 'nodejs';

const BodySchema = z.object({
  templateSlug: z.string(),
  tier: z.enum(['basic', 'premium']),
  locale: z.string().default('en')
});

export async function POST(req: Request) {
  const parsed = BodySchema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: 'Invalid request body' }, { status: 400 });
  }
  const { templateSlug, tier, locale } = parsed.data;

  const template = getTemplate(templateSlug);
  if (!template || !template.tiers.includes(tier as Tier)) {
    return NextResponse.json({ error: 'Unknown template or tier' }, { status: 404 });
  }

  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? 'http://localhost:7860';
  const admin = createSupabaseAdminClient();

  // Signed-in buyer if available; anonymous orders allowed for MVP.
  let userId: string | null = null;
  let email: string | undefined;
  try {
    const supabase = createSupabaseServerClient();
    const { data } = await supabase.auth.getUser();
    userId = data.user?.id ?? null;
    email = data.user?.email ?? undefined;
  } catch {
    /* auth not configured / anonymous */
  }

  const priceUsd = priceFor(template, tier as Tier);

  // 1) Create a pending order.
  const { data: order, error: orderErr } = await admin
    .from('orders')
    .insert({
      user_id: userId,
      template_slug: template.slug,
      tier_purchased: tier,
      amount: priceUsd,
      currency: 'usd',
      payment_provider: process.env.PAYMENT_PROVIDER ?? 'stripe',
      payment_status: 'pending'
    })
    .select('id')
    .single();

  if (orderErr || !order) {
    return NextResponse.json({ error: 'Could not create order' }, { status: 500 });
  }

  // 2) Create a collision-safe draft invite linked to the order.
  const base = coupleSlug(undefined, undefined, new Date().getFullYear());
  const slug = await ensureUniqueSlug(base, async (candidate) => {
    const { data } = await admin.from('invites').select('id').eq('slug', candidate).maybeSingle();
    return !!data;
  });

  const { data: invite, error: inviteErr } = await admin
    .from('invites')
    .insert({
      order_id: order.id,
      slug,
      status: 'draft',
      content_json: emptyInvite(template.slug, template.themes[0]?.key ?? 'sand')
    })
    .select('id')
    .single();

  if (inviteErr || !invite) {
    return NextResponse.json({ error: 'Could not create invite draft' }, { status: 500 });
  }

  // 3) Kick off payment via the configured provider (Stripe by default).
  try {
    const provider = getPaymentProvider();
    const { redirectUrl, providerRef } = await provider.createCheckout({
      orderId: order.id,
      templateName: template.name,
      tier,
      amount: Math.round(priceUsd * 100), // cents
      currency: 'usd',
      customerEmail: email,
      successUrl: `${siteUrl}/${locale}/checkout/success?invite=${invite.id}`,
      cancelUrl: `${siteUrl}/${locale}/checkout/cancel`
    });

    await admin.from('orders').update({ payment_ref: providerRef }).eq('id', order.id);

    return NextResponse.json({ redirectUrl });
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : 'Payment init failed' },
      { status: 500 }
    );
  }
}
