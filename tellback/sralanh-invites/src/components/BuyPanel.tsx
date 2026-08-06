'use client';

import { useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import type { TemplateMeta, Tier } from '@/data/templates';
import { priceFor } from '@/data/templates';

export function BuyPanel({ template }: { template: TemplateMeta }) {
  const t = useTranslations('template');
  const locale = useLocale();
  const [tier, setTier] = useState<Tier>('basic');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function buy() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ templateSlug: template.slug, tier, locale })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? 'Checkout failed');
      // Redirect to the payment provider's hosted checkout.
      window.location.href = data.redirectUrl;
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Checkout failed');
      setLoading(false);
    }
  }

  const tiers: { key: Tier; features: string }[] = [
    { key: 'basic', features: t('featuresBasic') },
    { key: 'premium', features: t('featuresPremium') }
  ];

  return (
    <div className="rounded-2xl border border-black/5 bg-white p-5 shadow-sm">
      <h2 className="font-medium">{t('chooseTier')}</h2>
      <div className="mt-4 space-y-3">
        {tiers.map((opt) => {
          const enabled = template.tiers.includes(opt.key);
          const price = priceFor(template, opt.key);
          return (
            <label
              key={opt.key}
              className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3 ${
                tier === opt.key ? 'border-brand-royal ring-1 ring-brand-royal' : 'border-black/10'
              } ${enabled ? '' : 'pointer-events-none opacity-40'}`}
            >
              <input
                type="radio"
                name="tier"
                className="mt-1"
                checked={tier === opt.key}
                disabled={!enabled}
                onChange={() => setTier(opt.key)}
              />
              <div className="flex-1">
                <div className="flex items-center justify-between">
                  <span className="font-medium capitalize">{opt.key}</span>
                  <span className="font-semibold">${price}</span>
                </div>
                <p className="mt-1 text-xs text-brand-ink/60">{opt.features}</p>
              </div>
            </label>
          );
        })}
      </div>

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      <button
        onClick={buy}
        disabled={loading}
        className="mt-4 w-full rounded-full bg-brand-royal px-5 py-3 font-medium text-white transition hover:opacity-90 disabled:opacity-50"
      >
        {loading ? '…' : t('buy')}
      </button>
      <p className="mt-2 text-center text-[11px] text-brand-ink/40">
        Stripe test mode — use card 4242 4242 4242 4242
      </p>
    </div>
  );
}
