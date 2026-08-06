/**
 * Slug helpers for personal, shareable invite URLs like
 *   /invite/dara-and-sopheak-2026
 * Collision-safe: callers append a short random suffix if the base is taken.
 */

const RESERVED = new Set(['api', 'invite', 'admin', 'editor', 'checkout', 'dashboard', 'templates']);

/** Latin-ise + kebab-case a string. Falls back to a generic token for pure Khmer input. */
export function slugify(input: string): string {
  const base = input
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '') // strip Latin diacritics
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)+/g, '');
  return base;
}

/**
 * Build the base slug for a couple, e.g.
 *   coupleSlug("Dara", "Sopheak", 2026) -> "dara-and-sopheak-2026"
 * If both names are Khmer-only (no Latin fallback), returns "our-wedding-2026".
 */
export function coupleSlug(groomLatin?: string, brideLatin?: string, year?: number): string {
  const g = groomLatin ? slugify(groomLatin) : '';
  const b = brideLatin ? slugify(brideLatin) : '';
  const y = year ?? new Date().getFullYear();
  let base = [g, b].filter(Boolean).join('-and-');
  if (!base) base = 'our-wedding';
  base = `${base}-${y}`;
  if (RESERVED.has(base)) base = `${base}-invite`;
  return base;
}

/** 5-char lowercase alphanumeric suffix (no ambiguous chars). */
export function shortSuffix(): string {
  const alphabet = 'abcdefghijkmnpqrstuvwxyz23456789';
  let out = '';
  for (let i = 0; i < 5; i++) {
    out += alphabet[Math.floor(Math.random() * alphabet.length)];
  }
  return out;
}

/**
 * Given a base slug and an async existence check, return a unique slug,
 * appending a short suffix on collision (retrying a few times).
 */
export async function ensureUniqueSlug(
  base: string,
  exists: (slug: string) => Promise<boolean>
): Promise<string> {
  if (RESERVED.has(base)) base = `${base}-invite`;
  if (!(await exists(base))) return base;
  for (let attempt = 0; attempt < 5; attempt++) {
    const candidate = `${base}-${shortSuffix()}`;
    if (!(await exists(candidate))) return candidate;
  }
  // Extremely unlikely fallback.
  return `${base}-${Date.now().toString(36)}`;
}
