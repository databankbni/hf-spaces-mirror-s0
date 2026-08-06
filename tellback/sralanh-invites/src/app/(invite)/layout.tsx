import '../globals.css';
import { fontVariables } from '@/app/fonts';

/**
 * Root layout for PUBLIC invite pages. Deliberately minimal and locale-agnostic
 * — no site header, no next-intl provider — so the couple's design fills the
 * whole viewport and links stay at /invite/<slug>. Per-invite <html lang> and
 * metadata are set in the page itself.
 */
export default function InviteRootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html className={fontVariables}>
      <body className="antialiased">{children}</body>
    </html>
  );
}
