import { getTranslations } from 'next-intl/server';
import { Link } from '@/i18n/routing';

export default async function CheckoutCancelPage() {
  const t = await getTranslations('checkout');
  return (
    <div className="mx-auto flex max-w-md flex-col items-center px-4 py-20 text-center">
      <div className="text-4xl">🕊️</div>
      <h1 className="mt-4 font-display text-3xl">{t('cancelTitle')}</h1>
      <p className="mt-2 text-brand-ink/60">{t('cancelBody')}</p>
      <Link href="/" className="mt-8 rounded-full bg-brand-ink px-6 py-3 font-medium text-white">
        {t('continue')}
      </Link>
    </div>
  );
}
