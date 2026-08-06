/**
 * Template catalog metadata. In production this mirrors rows in the `templates`
 * table; kept here as the canonical registry so the gallery, editor and invite
 * renderer stay in sync even before the DB is seeded.
 */

export type TemplateStyle = 'modern' | 'traditional' | 'floral' | 'minimalist' | 'royal';
export type TemplateLanguage = 'km' | 'en' | 'bilingual';
export type Tier = 'basic' | 'premium';

export interface ThemePreset {
  key: string;
  label: string;
  /** Swatch shown in the editor's constrained colour picker. */
  swatch: string;
}

export interface TemplateMeta {
  slug: string;
  name: string;
  description: string;
  styles: TemplateStyle[];
  languages: TemplateLanguage[];
  tags: string[];
  basePrice: number; // USD, Basic tier one-time
  tiers: Tier[];
  previewImage: string;
  /** Constrained palette presets — keeps designs looking good. */
  themes: ThemePreset[];
  /** Whether a working React component exists yet (vs a TODO stub). */
  implemented: boolean;
}

export const TEMPLATES: TemplateMeta[] = [
  {
    slug: 'modern-minimalist',
    name: 'Modern Minimalist',
    description:
      'Clean, neutral and elegant — works equally well for local and international couples. Generous whitespace, refined type.',
    styles: ['modern', 'minimalist'],
    languages: ['km', 'en', 'bilingual'],
    tags: ['modern', 'minimalist', 'neutral', 'bilingual'],
    basePrice: 12,
    tiers: ['basic', 'premium'],
    previewImage: '/templates/modern-minimalist/preview.svg',
    themes: [
      { key: 'sand', label: 'Sand', swatch: '#c9b79c' },
      { key: 'sage', label: 'Sage', swatch: '#8a9a7b' },
      { key: 'ink', label: 'Ink', swatch: '#2b2b2b' },
      { key: 'blush', label: 'Blush', swatch: '#d8a7a1' }
    ],
    implemented: true
  },
  {
    // TODO: build TraditionalKhmer.tsx (gold/deep red, Angkor-motif borders, Muol headings)
    slug: 'traditional-khmer',
    name: 'Traditional Khmer',
    description:
      'Gold and deep-red royal palette with ornamental Angkor-motif borders and Khmer Muol display headings.',
    styles: ['traditional', 'royal'],
    languages: ['km', 'bilingual'],
    tags: ['traditional', 'khmer', 'gold', 'royal'],
    basePrice: 15,
    tiers: ['basic', 'premium'],
    previewImage: '/templates/traditional-khmer/preview.svg',
    themes: [
      { key: 'gold-royal', label: 'Gold & Royal', swatch: '#b8912f' },
      { key: 'crimson', label: 'Crimson', swatch: '#7a1f2b' }
    ],
    implemented: true
  },
  {
    // TODO: build FloralRomantic.tsx (pastel palette, illustrated floral corners)
    slug: 'floral-romantic',
    name: 'Floral Romantic',
    description:
      'Soft pastel palette with illustrated floral corners — aimed at international and diaspora couples.',
    styles: ['floral'],
    languages: ['en', 'bilingual'],
    tags: ['floral', 'pastel', 'romantic', 'international'],
    basePrice: 12,
    tiers: ['basic', 'premium'],
    previewImage: '/templates/floral-romantic/preview.svg',
    themes: [
      { key: 'rose', label: 'Rose', swatch: '#e6b7c1' },
      { key: 'lavender', label: 'Lavender', swatch: '#c3b1d9' },
      { key: 'peony', label: 'Peony', swatch: '#f0c9d0' }
    ],
    implemented: true
  }
];

export const PRICE_TIERS = {
  basic: { label: 'Basic', hostingMonths: 3 },
  premium: { label: 'Premium', priceDelta: 18, hostingMonths: 12 },
  customAddon: { label: 'Custom design add-on', price: 40 }
} as const;

export function getTemplate(slug: string): TemplateMeta | undefined {
  return TEMPLATES.find((t) => t.slug === slug);
}

/** Price for a template at a given tier (Premium = base + delta). */
export function priceFor(meta: TemplateMeta, tier: Tier): number {
  return tier === 'premium' ? meta.basePrice + PRICE_TIERS.premium.priceDelta : meta.basePrice;
}
