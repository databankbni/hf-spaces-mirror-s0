import type { InviteContent } from '@/types/content';
import { eventDateTime } from './format';

/** Format a Date to the compact UTC form Google Calendar expects: YYYYMMDDTHHMMSSZ */
function toCalStamp(d: Date): string {
  return d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
}

/**
 * Build a "Add to Google Calendar" URL from the invite content. Defaults the
 * ceremony to a 3-hour block. Returns undefined if there's no date.
 */
export function addToCalendarUrl(content: InviteContent, title: string): string | undefined {
  const iso = eventDateTime(content);
  if (!iso) return undefined;
  const start = new Date(iso);
  if (Number.isNaN(start.getTime())) return undefined;
  const end = new Date(start.getTime() + 3 * 60 * 60 * 1000);

  const location = [content.event.venueName, content.event.venueAddress].filter(Boolean).join(', ');
  const params = new URLSearchParams({
    action: 'TEMPLATE',
    text: title,
    dates: `${toCalStamp(start)}/${toCalStamp(end)}`,
    details: content.event.lunarNote ?? ''
  });
  if (location) params.set('location', location);
  return `https://calendar.google.com/calendar/render?${params.toString()}`;
}
