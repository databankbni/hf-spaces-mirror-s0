'use client';

import { useLocale } from 'next-intl';
import { usePathname, useRouter } from '@/i18n/routing';
import { routing } from '@/i18n/routing';

const LABELS: Record<string, string> = { en: 'EN', km: 'ខ្មែរ' };

export function LocaleSwitcher() {
  const locale = useLocale();
  const pathname = usePathname();
  const router = useRouter();

  return (
    <div className="flex items-center gap-1 text-sm">
      {routing.locales.map((l) => (
        <button
          key={l}
          onClick={() => router.replace(pathname, { locale: l })}
          className={`rounded px-2 py-1 ${
            l === locale ? 'bg-brand-ink text-white' : 'text-brand-ink/70 hover:text-brand-ink'
          }`}
          aria-current={l === locale}
        >
          {LABELS[l] ?? l}
        </button>
      ))}
    </div>
  );
}
