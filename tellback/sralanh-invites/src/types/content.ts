import { z } from 'zod';

/**
 * The single source of truth for what lives inside `invites.content_json`.
 * Every template component receives exactly this shape as its `content` prop,
 * so the invite renderer is just: pick template component + hydrate with JSON.
 */

export const PersonSchema = z.object({
  nameKm: z.string().optional(),
  nameLatin: z.string().optional(),
  /** e.g. "Daughter of Mr Sok Dara & Mrs Chan Thida" — traditional in Khmer weddings. */
  parents: z.string().optional()
});

export const EventSchema = z.object({
  /** ISO date string, e.g. "2026-12-19" */
  dateGregorian: z.string().optional(),
  /** Free-text Buddhist-era / lunar note shown alongside the Gregorian date. */
  lunarNote: z.string().optional(),
  /** e.g. "16:00" */
  time: z.string().optional(),
  venueName: z.string().optional(),
  venueAddress: z.string().optional(),
  /** Google Maps embed URL (src of the iframe) or a maps share link. */
  mapUrl: z.string().optional()
});

export const InviteContentSchema = z.object({
  /** Which language(s) the couple filled in. Drives font stacks & layout. */
  language: z.enum(['km', 'en', 'bilingual']).default('bilingual'),
  /** Template registry slug, e.g. "modern-minimalist". */
  templateSlug: z.string(),
  /** Palette key constrained to the template's presets (see data/templates). */
  theme: z.string(),

  bride: PersonSchema.default({}),
  groom: PersonSchema.default({}),
  event: EventSchema.default({}),

  loveStory: z.string().optional(),
  /** Optional wedding hashtag, shown without the leading '#'. */
  hashtag: z.string().optional(),
  /** Public URLs (Supabase Storage). Max 8, enforced in the editor. */
  photos: z.array(z.string()).max(8).default([]),
  coverPhoto: z.string().optional(),

  // --- Premium (stubbed for MVP) ---
  rsvpEnabled: z.boolean().default(false),
  guestbookEnabled: z.boolean().default(false),
  musicUrl: z.string().optional()
});

export type Person = z.infer<typeof PersonSchema>;
export type InviteEvent = z.infer<typeof EventSchema>;
export type InviteContent = z.infer<typeof InviteContentSchema>;

/** Props every template component accepts. */
export interface TemplateProps {
  content: InviteContent;
}
