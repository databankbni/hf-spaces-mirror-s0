import { NextResponse } from 'next/server';
import { z } from 'zod';
import { InviteContentSchema } from '@/types/content';
import { createSupabaseAdminClient } from '@/lib/supabase/server';

export const runtime = 'nodejs';

const PatchSchema = z.object({
  content: InviteContentSchema,
  publish: z.boolean().optional(),
  // Premium: custom subdomain (stored; real DNS provisioning is a TODO).
  subdomain: z
    .string()
    .trim()
    .toLowerCase()
    .regex(/^[a-z0-9-]{3,40}$/)
    .optional()
    .or(z.literal(''))
});

// NOTE (MVP): edits are keyed by invite id via the service role. TODO: enforce
// ownership (order.user_id === auth.uid()) once buyer auth is wired end-to-end.
export async function PATCH(req: Request, { params }: { params: { id: string } }) {
  const body = await req.json().catch(() => null);
  const parsed = PatchSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: 'Invalid content' }, { status: 400 });
  }

  const admin = createSupabaseAdminClient();

  const { data: invite, error: fetchErr } = await admin
    .from('invites')
    .select('id, slug, order_id, status')
    .eq('id', params.id)
    .maybeSingle();

  if (fetchErr || !invite) {
    return NextResponse.json({ error: 'Invite not found' }, { status: 404 });
  }

  const update: Record<string, unknown> = { content_json: parsed.data.content };

  if (parsed.data.subdomain !== undefined) {
    update.subdomain = parsed.data.subdomain === '' ? null : parsed.data.subdomain;
  }

  if (parsed.data.publish) {
    // Determine hosting window from the order's tier.
    const { data: order } = await admin
      .from('orders')
      .select('tier_purchased, payment_status')
      .eq('id', invite.order_id)
      .maybeSingle();

    // TODO: require order.payment_status === 'paid' before publishing.
    const months = order?.tier_purchased === 'premium' ? 12 : 3;
    const expires = new Date();
    expires.setMonth(expires.getMonth() + months);

    update.status = 'published';
    update.published_at = new Date().toISOString();
    update.hosting_expires_at = expires.toISOString();
  }

  const { error: updErr } = await admin.from('invites').update(update).eq('id', params.id);
  if (updErr) {
    return NextResponse.json({ error: 'Could not save' }, { status: 500 });
  }

  return NextResponse.json({ ok: true, slug: invite.slug });
}
