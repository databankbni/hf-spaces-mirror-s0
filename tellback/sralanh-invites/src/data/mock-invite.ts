import type { InviteContent } from '@/types/content';

/**
 * Demo content used to render the gallery previews and the editor's initial
 * state before a buyer has entered anything.
 */
export const MOCK_INVITE: InviteContent = {
  language: 'bilingual',
  templateSlug: 'modern-minimalist',
  theme: 'sand',
  bride: {
    nameKm: 'សុភា',
    nameLatin: 'Sopheak',
    parents: 'Daughter of Mr Chan Sophal & Mrs Meas Kunthea'
  },
  groom: {
    nameKm: 'តារា',
    nameLatin: 'Dara',
    parents: 'Son of Mr Sok Vibol & Mrs Yin Sreymom'
  },
  event: {
    dateGregorian: '2026-12-19',
    lunarNote: 'ថ្ងៃសៅរ៍ ១ រោច ខែបុស្ស ឆ្នាំម្សាញ់',
    time: '16:00',
    venueName: 'Sofitel Phnom Penh Phokeethra',
    venueAddress: '26 Old August Site, Sothearos Blvd, Phnom Penh',
    mapUrl: 'https://www.google.com/maps?q=Sofitel+Phnom+Penh+Phokeethra&output=embed'
  },
  loveStory:
    'From a chance meeting in Phnom Penh to a lifetime together — we would be honoured to have you celebrate this day with us.',
  hashtag: 'DaraAndSopheak2026',
  photos: [],
  coverPhoto: undefined,
  rsvpEnabled: false,
  guestbookEnabled: false
};

/** Blank draft for a freshly purchased template of the given slug/theme. */
export function emptyInvite(templateSlug: string, theme: string): InviteContent {
  return {
    language: 'bilingual',
    templateSlug,
    theme,
    bride: {},
    groom: {},
    event: {},
    photos: [],
    rsvpEnabled: false,
    guestbookEnabled: false
  };
}
