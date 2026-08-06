import { getTranslations } from 'next-intl/server';
import { Link } from '@/i18n/routing';
import { createSupabaseServerClient } from '@/lib/supabase/server';

export const dynamic = 'force-dynamic';

type InviteRow = { id: string; slug: string; status: string; hosting_expires_at: string | null };
type OrderRow = {
  id: string;
  tier_purchased: string;
  template_slug: string | null;
  payment_status: string;
  created_at: string;
  invites: InviteRow[] | null;
};

export default async function DashboardPage() {
  const t = await getTranslations('nav');
  const supabase = createSupabaseServerClient();

  const {
    data: { user }
  } = await supabase.auth.getUser();

  if (!user) {
    return (
      <div className="mx-auto max-w-md px-4 py-20 text-center">
        <h1 className="font-display text-2xl">{t('dashboard')}</h1>
        <Link
          href="/login"
          className="mt-6 inline-block rounded-full bg-brand-royal px-6 py-3 font-medium text-white"
        >
          {t('login')}
        </Link>
      </div>
    );
  }

  // RLS limits orders to the signed-in buyer; invites are nested via FK.
  const { data: orders } = await supabase
    .from('orders')
    .select('id, tier_purchased, template_slug, payment_status, created_at, invites(id, slug, status, hosting_expires_at)')
    .order('created_at', { ascending: false });

  const inviteIds = ((orders as OrderRow[]) ?? [])
    .flatMap((o) => o.invites ?? [])
    .map((i) => i.id);

  // RSVP counts per invite (owner can read via RLS).
  const rsvpCounts = new Map<string, number>();
  if (inviteIds.length) {
    const { data: rsvps } = await supabase.from('rsvps').select('invite_id').in('invite_id', inviteIds);
    for (const r of (rsvps as { invite_id: string }[]) ?? []) {
      rsvpCounts.set(r.invite_id, (rsvpCounts.get(r.invite_id) ?? 0) + 1);
    }
  }

  const rows = (orders as OrderRow[]) ?? [];

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <h1 className="font-display text-3xl">{t('dashboard')}</h1>
      <p className="mt-1 text-sm text-brand-ink/50">{user.email}</p>

      {rows.length === 0 && (
        <p className="mt-10 rounded-xl bg-black/5 p-6 text-center text-sm text-brand-ink/60">
          No invitations yet.{' '}
          <Link href="/" className="text-brand-royal underline">
            Browse templates
          </Link>
        </p>
      )}

      <div className="mt-8 space-y-4">
        {rows.map((order) =>
          (order.invites ?? []).map((invite) => (
            <div
              key={invite.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-black/10 bg-white p-4"
            >
              <div>
                <p className="font-medium">{order.template_slug ?? 'Invitation'}</p>
                <p className="mt-0.5 text-xs text-brand-ink/50">
                  <span className="capitalize">{order.tier_purchased}</span> ·{' '}
                  <StatusBadge status={invite.status} /> · {rsvpCounts.get(invite.id) ?? 0} RSVPs
                  {invite.hosting_expires_at && (
                    <> · expires {new Date(invite.hosting_expires_at).toLocaleDateString()}</>
                  )}
                </p>
              </div>
              <div className="flex items-center gap-3 text-sm">
                <Link href={`/editor/${invite.id}`} className="text-brand-royal underline">
                  Edit
                </Link>
                {invite.status === 'published' && (
                  <a href={`/invite/${invite.slug}`} target="_blank" rel="noreferrer" className="underline">
                    View live
                  </a>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const color =
    status === 'published' ? 'text-green-600' : status === 'expired' ? 'text-red-500' : 'text-amber-600';
  return <span className={`capitalize ${color}`}>{status}</span>;
}
