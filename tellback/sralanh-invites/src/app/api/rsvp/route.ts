import { NextResponse } from 'next/server';
import { z } from 'zod';
import { createSupabaseAdminClient } from '@/lib/supabase/server';
import { rateLimit, clientIp } from '@/lib/rate-limit';

export const runtime = 'nodejs';

// Premium feature — endpoint is wired (table + rate limit) but the public UI is
// a TODO. Guests POST here from the invite page once RSVP is enabled.
const RsvpSchema = z.object({
  inviteId: z.string().uuid(),
  guestName: z.string().min(1).max(120),
  attending: z.boolean(),
  guestCount: z.number().int().min(1).max(20).default(1),
  mealPref: z.string().max(120).optional(),
  note: z.string().max(500).optional()
});

export async function POST(req: Request) {
  const limit = rateLimit(`rsvp:${clientIp(req)}`, { limit: 5, windowMs: 60_000 });
  if (!limit.ok) {
    return NextResponse.json(
      { error: 'Too many submissions, please slow down.' },
      { status: 429, headers: { 'Retry-After': String(limit.retryAfterSeconds) } }
    );
  }

  const parsed = RsvpSchema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: 'Invalid RSVP' }, { status: 400 });
  }

  const admin = createSupabaseAdminClient();
  const { error } = await admin.from('rsvps').insert({
    invite_id: parsed.data.inviteId,
    guest_name: parsed.data.guestName,
    attending: parsed.data.attending,
    guest_count: parsed.data.guestCount,
    meal_pref: parsed.data.mealPref,
    note: parsed.data.note
  });

  if (error) return NextResponse.json({ error: 'Could not save RSVP' }, { status: 500 });
  return NextResponse.json({ ok: true });
}
