import { getTranslations } from 'next-intl/server';
import { Link } from '@/i18n/routing';

export default async function CheckoutSuccessPage({
  searchParams
}: {
  searchParams: { invite?: string };
}) {
  const t = await getTranslations('checkout');
  const inviteId = searchParams.invite;

  return (
    <div className="mx-auto flex max-w-md flex-col items-center px-4 py-20 text-center">
      <div className="text-5xl">💌</div>
      <h1 className="mt-4 font-display text-3xl">{t('successTitle')}</h1>
      <p className="mt-2 text-brand-ink/60">{t('successBody')}</p>
      {inviteId && (
        <Link
          href={`/editor/${inviteId}`}
          className="mt-8 rounded-full bg-brand-royal px-6 py-3 font-medium text-white hover:opacity-90"
        >
          {t('continue')}
        </Link>
      )}
    </div>
  );
}
