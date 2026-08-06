import { getTranslations } from 'next-intl/server';
import { Link } from '@/i18n/routing';
import { LocaleSwitcher } from './LocaleSwitcher';
import { createSupabaseServerClient } from '@/lib/supabase/server';

export async function SiteHeader() {
  const t = await getTranslations('nav');

  let userEmail: string | null = null;
  try {
    const supabase = createSupabaseServerClient();
    const { data } = await supabase.auth.getUser();
    userEmail = data.user?.email ?? null;
  } catch {
    /* auth not configured */
  }

  return (
    <header className="sticky top-0 z-20 border-b border-black/5 bg-white/80 backdrop-blur">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
        <Link href="/" className="font-display text-xl font-semibold">
          SraLanh Invites
        </Link>
        <nav className="flex items-center gap-4 text-sm">
          <Link href="/" className="hover:opacity-70">
            {t('gallery')}
          </Link>
          {userEmail ? (
            <>
              <Link href="/dashboard" className="hover:opacity-70">
                {t('dashboard')}
              </Link>
              <form action="/api/auth/signout" method="post">
                <button type="submit" className="text-brand-ink/70 hover:text-brand-ink">
                  {t('signout')}
                </button>
              </form>
            </>
          ) : (
            <Link href="/login" className="hover:opacity-70">
              {t('login')}
            </Link>
          )}
          <LocaleSwitcher />
        </nav>
      </div>
    </header>
  );
}
