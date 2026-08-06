import { NextResponse } from 'next/server';
import { z } from 'zod';
import { createSupabaseAdminClient } from '@/lib/supabase/server';
import { rateLimit, clientIp } from '@/lib/rate-limit';

export const runtime = 'nodejs';

// Premium feature — endpoint wired, public wishes-wall UI is a TODO.
const EntrySchema = z.object({
  inviteId: z.string().uuid(),
  name: z.string().min(1).max(120),
  message: z.string().min(1).max(500)
});

export async function POST(req: Request) {
  const limit = rateLimit(`guestbook:${clientIp(req)}`, { limit: 5, windowMs: 60_000 });
  if (!limit.ok) {
    return NextResponse.json(
      { error: 'Too many submissions, please slow down.' },
      { status: 429, headers: { 'Retry-After': String(limit.retryAfterSeconds) } }
    );
  }

  const parsed = EntrySchema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: 'Invalid entry' }, { status: 400 });
  }

  const admin = createSupabaseAdminClient();
  const { error } = await admin.from('guestbook_entries').insert({
    invite_id: parsed.data.inviteId,
    name: parsed.data.name,
    message: parsed.data.message
  });

  if (error) return NextResponse.json({ error: 'Could not save entry' }, { status: 500 });
  return NextResponse.json({ ok: true });
}
