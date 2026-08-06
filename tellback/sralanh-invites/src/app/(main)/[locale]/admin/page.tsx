import { getTranslations } from 'next-intl/server';
import { Link } from '@/i18n/routing';
import { createSupabaseServerClient, createSupabaseAdminClient } from '@/lib/supabase/server';

export const dynamic = 'force-dynamic';

export default async function AdminPage() {
  const tNav = await getTranslations('nav');
  const tAuth = await getTranslations('auth');
  const supabase = createSupabaseServerClient();

  const {
    data: { user }
  } = await supabase.auth.getUser();

  if (!user) {
    return (
      <div className="mx-auto max-w-md px-4 py-20 text-center">
        <h1 className="font-display text-2xl">{tNav('admin')}</h1>
        <Link href="/login" className="mt-6 inline-block rounded-full bg-brand-royal px-6 py-3 text-white">
          {tNav('login')}
        </Link>
      </div>
    );
  }

  // Gate on the users.role flag (set manually in the DB for now).
  const { data: profile } = await supabase.from('users').select('role').eq('id', user.id).maybeSingle();
  if (profile?.role !== 'admin') {
    return (
      <div className="mx-auto max-w-md px-4 py-20 text-center text-brand-ink/60">{tAuth('notAuthorized')}</div>
    );
  }

  // Verified admin -> use the service role to read aggregate data.
  const admin = createSupabaseAdminClient();
  const [{ data: orders }, { data: invites }, { data: requests }, { data: templates }] = await Promise.all([
    admin.from('orders').select('amount, currency, template_slug, payment_status'),
    admin.from('invites').select('status'),
    admin
      .from('custom_design_requests')
      .select('id, brief_text, status, created_at')
      .order('created_at', { ascending: false }),
    admin.from('templates').select('slug, name, base_price, is_active')
  ]);

  const paid = ((orders as { amount: number; payment_status: string; template_slug: string | null }[]) ?? []).filter(
    (o) => o.payment_status === 'paid'
  );
  const totalRevenue = paid.reduce((s, o) => s + Number(o.amount), 0);

  const revenueByTemplate = new Map<string, { count: number; revenue: number }>();
  for (const o of paid) {
    const key = o.template_slug ?? 'unknown';
    const cur = revenueByTemplate.get(key) ?? { count: 0, revenue: 0 };
    revenueByTemplate.set(key, { count: cur.count + 1, revenue: cur.revenue + Number(o.amount) });
  }

  const inviteStatus = { draft: 0, published: 0, expired: 0 } as Record<string, number>;
  for (const i of (invites as { status: string }[]) ?? []) inviteStatus[i.status] = (inviteStatus[i.status] ?? 0) + 1;

  return (
    <div className="mx-auto max-w-4xl px-4 py-10">
      <h1 className="font-display text-3xl">{tNav('admin')}</h1>

      {/* KPIs */}
      <div className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Kpi label="Revenue (paid)" value={`$${totalRevenue.toFixed(2)}`} />
        <Kpi label="Paid orders" value={String(paid.length)} />
        <Kpi label="Published" value={String(inviteStatus.published ?? 0)} />
        <Kpi label="Expired" value={String(inviteStatus.expired ?? 0)} />
      </div>

      {/* Revenue by template */}
      <h2 className="mt-10 text-sm font-semibold uppercase tracking-wide text-brand-ink/60">
        Revenue by template
      </h2>
      <div className="mt-3 overflow-hidden rounded-xl border border-black/10">
        <table className="w-full text-sm">
          <thead className="bg-black/5 text-left">
            <tr>
              <th className="px-4 py-2">Template</th>
              <th className="px-4 py-2">Sales</th>
              <th className="px-4 py-2">Revenue</th>
            </tr>
          </thead>
          <tbody>
            {((templates as { slug: string; name: string }[]) ?? []).map((tpl) => {
              const r = revenueByTemplate.get(tpl.slug) ?? { count: 0, revenue: 0 };
              return (
                <tr key={tpl.slug} className="border-t border-black/5">
                  <td className="px-4 py-2">{tpl.name}</td>
                  <td className="px-4 py-2">{r.count}</td>
                  <td className="px-4 py-2">${r.revenue.toFixed(2)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Custom design request queue */}
      <h2 className="mt-10 text-sm font-semibold uppercase tracking-wide text-brand-ink/60">
        Custom design requests
      </h2>
      <div className="mt-3 space-y-2">
        {((requests as { id: string; brief_text: string | null; status: string; created_at: string }[]) ?? [])
          .length === 0 && <p className="text-sm text-brand-ink/50">No requests.</p>}
        {((requests as { id: string; brief_text: string | null; status: string; created_at: string }[]) ?? []).map(
          (req) => (
            <div
              key={req.id}
              className="flex items-center justify-between rounded-lg border border-black/10 bg-white p-3 text-sm"
            >
              <span className="line-clamp-1">{req.brief_text ?? '(no brief)'}</span>
              <span className="ml-3 shrink-0 rounded-full bg-black/5 px-2 py-0.5 text-xs capitalize">
                {req.status}
              </span>
            </div>
          )
        )}
      </div>

      {/* TODO: template upload form (writes to templates table + preview images to Storage). */}
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-black/10 bg-white p-4">
      <p className="text-2xl font-semibold">{value}</p>
      <p className="mt-1 text-xs text-brand-ink/50">{label}</p>
    </div>
  );
}
