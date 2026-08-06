import '../../globals.css';
import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { NextIntlClientProvider } from 'next-intl';
import { getMessages } from 'next-intl/server';
import { routing, type AppLocale } from '@/i18n/routing';
import { fontVariables } from '@/app/fonts';
import { SiteHeader } from '@/components/SiteHeader';

export const metadata: Metadata = {
  title: 'SraLanh Invites',
  description: 'Bilingual (Khmer/English) digital wedding invitations.'
};

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export default async function LocaleLayout({
  children,
  params: { locale }
}: {
  children: React.ReactNode;
  params: { locale: string };
}) {
  if (!routing.locales.includes(locale as AppLocale)) notFound();

  // Loads messages for the active locale (see src/i18n/request.ts).
  const messages = await getMessages();

  return (
    <html lang={locale} className={fontVariables}>
      <body className="min-h-screen bg-[#faf8f5] font-sans text-brand-ink antialiased">
        <NextIntlClientProvider messages={messages}>
          <SiteHeader />
          <main>{children}</main>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
