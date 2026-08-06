import Image from 'next/image';
import type { TemplateProps } from '@/types/content';
import { Countdown } from '@/components/invite/Countdown';
import { BackgroundMusic } from '@/components/invite/BackgroundMusic';
import {
  personName,
  formatTime,
  toEmbedMapUrl,
  eventDateTime,
  dateParts,
  monogram
} from '@/lib/format';
import { addToCalendarUrl } from '@/lib/calendar';
import { inviteLabels } from '@/lib/invite-labels';

/** Soft pastel palettes (keys match data/templates.ts). */
const PALETTES: Record<string, { bg: string; text: string; accent: string; soft: string }> = {
  rose: { bg: '#fdf4f5', text: '#5b3b45', accent: '#c97b8b', soft: '#f3d9df' },
  lavender: { bg: '#f6f3fb', text: '#4a3f5c', accent: '#9b83c4', soft: '#e2d7f2' },
  peony: { bg: '#fdf1f4', text: '#5c3a48', accent: '#d98098', soft: '#f7d6df' }
};

/** Illustrated floral corner. */
function Floral({ className, color, soft }: { className?: string; color: string; soft: string }) {
  return (
    <svg viewBox="0 0 120 120" className={className} aria-hidden>
      <g fill="none" stroke={color} strokeWidth={1.5} strokeLinecap="round">
        <path d="M8 60 Q30 40 20 14 Q44 30 60 12" opacity={0.7} />
        <path d="M14 40 Q34 44 40 62" opacity={0.5} />
      </g>
      <g fill={soft} stroke={color} strokeWidth={1}>
        <circle cx="20" cy="14" r="6" />
        <circle cx="60" cy="12" r="7" />
        <circle cx="40" cy="62" r="5" />
        <circle cx="12" cy="40" r="4" />
      </g>
      <g fill={color}>
        <circle cx="20" cy="14" r="2" />
        <circle cx="60" cy="12" r="2.5" />
        <circle cx="40" cy="62" r="1.8" />
      </g>
    </svg>
  );
}

function Sprig({ color, soft }: { color: string; soft: string }) {
  return (
    <div className="my-8 flex items-center justify-center gap-2" aria-hidden>
      <span className="h-px w-12" style={{ backgroundColor: color, opacity: 0.4 }} />
      <svg width="30" height="16" viewBox="0 0 30 16" fill="none">
        <path d="M2 8 H28" stroke={color} strokeWidth={1} opacity={0.5} />
        <circle cx="10" cy="8" r="3.5" fill={soft} stroke={color} />
        <circle cx="20" cy="8" r="3.5" fill={soft} stroke={color} />
        <circle cx="15" cy="4" r="2.5" fill={color} opacity={0.8} />
      </svg>
      <span className="h-px w-12" style={{ backgroundColor: color, opacity: 0.4 }} />
    </div>
  );
}

/**
 * Floral Romantic — soft pastels, illustrated floral corners. Aimed at
 * international / diaspora couples. Renders from the `content` JSON, mobile-first.
 */
export default function FloralRomantic({ content }: TemplateProps) {
  const p = PALETTES[content.theme] ?? PALETTES.rose;
  const L = inviteLabels(content.language);
  const bride = personName(content.bride, content.language);
  const groom = personName(content.groom, content.language);
  const dp = dateParts(content.event.dateGregorian, content.language);
  const timeStr = formatTime(content.event.time, content.language);
  const mapEmbed = toEmbedMapUrl(content.event.mapUrl);
  const isKhmer = content.language === 'km';
  const title = `${groom.primary} & ${bride.primary} — Wedding`;
  const calUrl = addToCalendarUrl(content, title);

  return (
    <div className={isKhmer ? 'font-khmer' : 'font-sans'} style={{ backgroundColor: p.bg, color: p.text }}>
      <div className="relative mx-auto max-w-2xl px-5 py-14 sm:py-20">
        <Floral className="pointer-events-none absolute left-0 top-0 h-24 w-24" color={p.accent} soft={p.soft} />
        <Floral
          className="pointer-events-none absolute right-0 top-0 h-24 w-24 -scale-x-100"
          color={p.accent}
          soft={p.soft}
        />

        {/* Hero */}
        <header className="text-center">
          <p className="font-display text-lg italic" style={{ color: p.accent }}>
            {L.saveTheDate}
          </p>
          <div
            className="mx-auto mt-4 flex h-16 w-16 items-center justify-center rounded-full text-sm"
            style={{ backgroundColor: p.soft, color: p.accent }}
          >
            {monogram(groom.primary, bride.primary)}
          </div>

          <div className="mt-6">
            <h1 className="font-display text-4xl sm:text-6xl">{groom.primary}</h1>
            {groom.secondary && (
              <p className="mt-1 font-khmer text-xl" style={{ color: p.accent }}>
                {groom.secondary}
              </p>
            )}
            {content.groom.parents && <p className="mt-1 text-xs opacity-60">{content.groom.parents}</p>}

            <div className="my-3 font-display text-3xl" style={{ color: p.accent }}>
              {L.and}
            </div>

            <h1 className="font-display text-4xl sm:text-6xl">{bride.primary}</h1>
            {bride.secondary && (
              <p className="mt-1 font-khmer text-xl" style={{ color: p.accent }}>
                {bride.secondary}
              </p>
            )}
            {content.bride.parents && <p className="mt-1 text-xs opacity-60">{content.bride.parents}</p>}
          </div>

          <p className="mt-5 text-xs uppercase tracking-[0.2em] opacity-50">{L.withFamilies}</p>

          {content.rsvpEnabled && (
            <a
              href="#rsvp"
              className="mt-7 inline-block rounded-full px-6 py-2.5 text-sm text-white"
              style={{ backgroundColor: p.accent }}
            >
              {L.rsvp}
            </a>
          )}
        </header>

        {content.coverPhoto && (
          <div className="mt-8 overflow-hidden rounded-[2rem]">
            <Image
              src={content.coverPhoto}
              alt=""
              width={1200}
              height={1500}
              className="h-auto w-full object-cover"
              priority
            />
          </div>
        )}

        <Sprig color={p.accent} soft={p.soft} />

        {/* When */}
        <section className="text-center">
          <h2 className="font-display text-2xl" style={{ color: p.accent }}>
            {L.when}
          </h2>
          {dp ? (
            <div
              className="mx-auto mt-4 w-fit rounded-2xl px-8 py-5"
              style={{ backgroundColor: p.soft }}
            >
              <p className="text-sm opacity-70">{dp.weekday}</p>
              <p className="font-display text-4xl">{dp.day}</p>
              <p className="text-lg">{dp.month} {dp.year}</p>
              {timeStr && <p className="mt-1 text-sm opacity-80">{timeStr}</p>}
              {content.event.lunarNote && (
                <p className="mt-2 font-khmer text-xs opacity-70">{content.event.lunarNote}</p>
              )}
            </div>
          ) : (
            <p className="mt-3 opacity-50">—</p>
          )}
          <div className="mt-6">
            <Countdown target={eventDateTime(content)} labels={L.countdown} />
          </div>
        </section>

        {/* Where */}
        {(content.event.venueName || mapEmbed) && (
          <section className="mt-12 text-center">
            <h2 className="font-display text-2xl" style={{ color: p.accent }}>
              {L.venue}
            </h2>
            {content.event.venueName && <p className="mt-3 text-lg">{content.event.venueName}</p>}
            {content.event.venueAddress && (
              <p className="mt-1 text-sm opacity-80">{content.event.venueAddress}</p>
            )}
            <div className="mt-4 flex flex-wrap items-center justify-center gap-3">
              {calUrl && (
                <a
                  href={calUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-full border px-5 py-2 text-sm"
                  style={{ borderColor: p.accent, color: p.accent }}
                >
                  {L.addToCalendar}
                </a>
              )}
              {content.event.mapUrl && (
                <a
                  href={content.event.mapUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-full px-5 py-2 text-sm text-white"
                  style={{ backgroundColor: p.accent }}
                >
                  {L.getDirections}
                </a>
              )}
            </div>
            {mapEmbed && (
              <div className="mt-5 overflow-hidden rounded-2xl">
                <iframe title="map" src={mapEmbed} className="h-64 w-full" loading="lazy" />
              </div>
            )}
          </section>
        )}

        {content.loveStory && (
          <section className="mt-12 text-center">
            <Sprig color={p.accent} soft={p.soft} />
            <h2 className="font-display text-2xl" style={{ color: p.accent }}>
              {L.ourStory}
            </h2>
            <p className="mx-auto mt-3 max-w-prose leading-relaxed opacity-90">{content.loveStory}</p>
          </section>
        )}

        {content.photos.length > 0 && (
          <section className="mt-12 grid grid-cols-2 gap-3 sm:grid-cols-3">
            {content.photos.map((src, i) => (
              <div key={i} className="aspect-square overflow-hidden rounded-2xl">
                <Image src={src} alt="" width={600} height={600} className="h-full w-full object-cover" />
              </div>
            ))}
          </section>
        )}

        <footer className="mt-14 text-center">
          <Sprig color={p.accent} soft={p.soft} />
          <p className="text-sm" style={{ color: p.accent }}>
            {L.thankYou}
          </p>
          <p className="mt-2 font-display text-2xl">
            {groom.primary} {L.and} {bride.primary}
          </p>
          {content.hashtag && (
            <p className="mt-2 text-xs uppercase tracking-widest opacity-50">
              #{content.hashtag.replace(/^#/, '')}
            </p>
          )}
        </footer>
      </div>

      {content.musicUrl && <BackgroundMusic src={content.musicUrl} color={p.accent} />}
    </div>
  );
}
