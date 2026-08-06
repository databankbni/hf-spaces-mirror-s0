import type { InviteContent, Person } from '@/types/content';

/**
 * Display a person's name honouring the invite's language mode.
 *  - 'km'        -> Khmer name (falls back to Latin)
 *  - 'en'        -> Latin name (falls back to Khmer)
 *  - 'bilingual' -> both, when available
 */
export function personName(
  p: Person,
  language: InviteContent['language']
): { primary: string; secondary?: string } {
  const km = p.nameKm?.trim();
  const latin = p.nameLatin?.trim();

  if (language === 'km') return { primary: km || latin || '' };
  if (language === 'en') return { primary: latin || km || '' };
  // bilingual
  if (km && latin) return { primary: latin, secondary: km };
  return { primary: latin || km || '' };
}

/** Gregorian date formatted for the given locale. Khmer uses km-KH digits/months. */
export function formatEventDate(iso: string | undefined, language: InviteContent['language']): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const locale = language === 'km' ? 'km-KH' : 'en-GB';
  return new Intl.DateTimeFormat(locale, {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  }).format(d);
}

/** "16:00" -> localized time; passes through if unparseable. */
export function formatTime(time: string | undefined, language: InviteContent['language']): string {
  if (!time) return '';
  const m = /^(\d{1,2}):(\d{2})$/.exec(time);
  if (!m) return time;
  const d = new Date();
  d.setHours(Number(m[1]), Number(m[2]), 0, 0);
  const locale = language === 'km' ? 'km-KH' : 'en-GB';
  return new Intl.DateTimeFormat(locale, { hour: 'numeric', minute: '2-digit' }).format(d);
}

/** Combine the event date + optional "HH:MM" time into one ISO string. */
export function eventDateTime(content: InviteContent): string | undefined {
  const { dateGregorian, time } = content.event;
  if (!dateGregorian) return undefined;
  if (time && /^\d{1,2}:\d{2}$/.test(time)) return `${dateGregorian}T${time.padStart(5, '0')}:00`;
  return dateGregorian;
}

/** Split a date into day / month / year parts for a formal "save the date" block. */
export function dateParts(
  iso: string | undefined,
  language: InviteContent['language']
): { day: string; month: string; year: string; weekday: string } | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const locale = language === 'km' ? 'km-KH' : 'en-GB';
  const fmt = (opts: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat(locale, opts).format(d);
  return {
    day: fmt({ day: '2-digit' }),
    month: fmt({ month: 'long' }),
    year: fmt({ year: 'numeric' }),
    weekday: fmt({ weekday: 'long' })
  };
}

/** First grapheme of a string (handles Khmer clusters reasonably). */
export function firstLetter(str: string | undefined): string {
  if (!str) return '';
  return Array.from(str.trim())[0] ?? '';
}

/** Couple monogram, e.g. "D & S" from the display names. */
export function monogram(a: string, b: string): string {
  const l = firstLetter(a).toUpperCase();
  const r = firstLetter(b).toUpperCase();
  if (!l && !r) return '';
  return `${l} & ${r}`;
}

/** Normalise a Google Maps link/embed URL into an iframe-embeddable src. */
export function toEmbedMapUrl(url: string | undefined): string | undefined {
  if (!url) return undefined;
  if (url.includes('output=embed') || url.includes('/embed')) return url;
  // Best-effort: turn a plain query/share link into an embed.
  try {
    const u = new URL(url);
    const q = u.searchParams.get('q') ?? u.pathname;
    return `https://www.google.com/maps?q=${encodeURIComponent(q)}&output=embed`;
  } catch {
    return `https://www.google.com/maps?q=${encodeURIComponent(url)}&output=embed`;
  }
}
