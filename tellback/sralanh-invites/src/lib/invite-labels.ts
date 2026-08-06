import type { InviteContent } from '@/types/content';

/**
 * The public invite page is locale-agnostic (no /en|/km prefix), so template
 * chrome labels come from here based on the couple's chosen `language` rather
 * than from next-intl. For 'bilingual' we default the chrome to English while
 * the couple's names render in both scripts.
 */
export interface InviteLabels {
  saveTheDate: string;
  youAreInvited: string;
  withFamilies: string;
  and: string;
  when: string;
  venue: string;
  getDirections: string;
  addToCalendar: string;
  ourStory: string;
  rsvp: string;
  thankYou: string;
  countdown: { days: string; hours: string; minutes: string; seconds: string };
}

const EN: InviteLabels = {
  saveTheDate: 'Save the date',
  youAreInvited: 'You are invited to the wedding of',
  withFamilies: 'Together with their families',
  and: '&',
  when: 'When',
  venue: 'Venue',
  getDirections: 'Get directions',
  addToCalendar: 'Add to calendar',
  ourStory: 'Our story',
  rsvp: 'RSVP',
  thankYou: 'With love and gratitude',
  countdown: { days: 'days', hours: 'hours', minutes: 'minutes', seconds: 'seconds' }
};

const KM: InviteLabels = {
  saveTheDate: 'កត់ត្រាថ្ងៃនេះ',
  youAreInvited: 'សូមគោរពអញ្ជើញចូលរួមក្នុងពិធីមង្គលការរបស់',
  withFamilies: 'ដោយមានការចូលរួមពីគ្រួសារទាំងសងខាង',
  and: 'និង',
  when: 'ពេលវេលា',
  venue: 'ទីកន្លែង',
  getDirections: 'មើលទិសដៅ',
  addToCalendar: 'បញ្ចូលទៅប្រតិទិន',
  ourStory: 'រឿងស្នេហ៍របស់យើង',
  rsvp: 'ឆ្លើយតប',
  thankYou: 'ដោយក្តីស្រឡាញ់ និងអំណរគុណ',
  countdown: { days: 'ថ្ងៃ', hours: 'ម៉ោង', minutes: 'នាទី', seconds: 'វិនាទី' }
};

export function inviteLabels(language: InviteContent['language']): InviteLabels {
  return language === 'km' ? KM : EN;
}
