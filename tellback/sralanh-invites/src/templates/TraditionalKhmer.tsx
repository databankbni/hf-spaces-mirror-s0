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

/** Gold/deep-red royal palettes (keys match data/templates.ts). */
const PALETTES: Record<string, { bg: string; panel: string; text: string; gold: string }> = {
  'gold-royal': { bg: '#3a0d12', panel: '#4a1119', text: '#f5e6c8', gold: '#c9a24a' },
  crimson: { bg: '#2b0a0e', panel: '#3d0f14', text: '#f3e2c7', gold: '#d4af5a' }
};

/** Ornamental Angkor-style corner flourish. */
function Corner({ className, color }: { className?: string; color: string }) {
  return (
    <svg viewBox="0 0 100 100" className={className} fill="none" stroke={color} strokeWidth={2} aria-hidden>
      <path d="M2 40 Q2 2 40 2" strokeLinecap="round" />
      <path d="M12 40 Q12 12 40 12" strokeLinecap="round" opacity={0.6} />
      <circle cx="40" cy="12" r="3" fill={color} stroke="none" />
      <circle cx="12" cy="40" r="3" fill={color} stroke="none" />
      <path d="M20 20 q10 -6 16 2 q-8 -2 -16 -2Z" fill={color} stroke="none" opacity={0.8} />
    </svg>
  );
}

/** Gold ornamental divider (kbach-style). */
function GoldDivider({ color }: { color: string }) {
  return (
    <div className="my-8 flex items-center justify-center gap-3" aria-hidden>
      <span className="h-px w-14" style={{ backgroundColor: color, opacity: 0.5 }} />
      <svg width="26" height="14" viewBox="0 0 26 14" fill="none" stroke={color} strokeWidth={1.5}>
        <path d="M13 1 C17 5 21 5 25 7 C21 9 17 9 13 13 C9 9 5 9 1 7 C5 5 9 5 13 1Z" fill={color} opacity={0.85} />
      </svg>
      <span className="h-px w-14" style={{ backgroundColor: color, opacity: 0.5 }} />
    </div>
  );
}

/**
 * Traditional Khmer — gold on deep red, ornamental borders, Khmer Muol display
 * headings (font-moul). Renders entirely from the `content` JSON. Mobile-first.
 */
export default function TraditionalKhmer({ content }: TemplateProps) {
  const p = PALETTES[content.theme] ?? PALETTES['gold-royal'];
  const L = inviteLabels(content.language);
  const bride = personName(content.bride, content.language);
  const groom = personName(content.groom, content.language);
  const dp = dateParts(content.event.dateGregorian, content.language);
  const timeStr = formatTime(content.event.time, content.language);
  const mapEmbed = toEmbedMapUrl(content.event.mapUrl);
  const title = `${groom.primary} & ${bride.primary} — Wedding`;
  const calUrl = addToCalendarUrl(content, title);

  return (
    <div className="font-khmer" style={{ backgroundColor: p.bg, color: p.text }}>
      <div className="mx-auto max-w-2xl px-5 py-12 sm:py-16">
        {/* Ornamental framed header */}
        <div className="relative rounded-lg p-8 sm:p-12" style={{ border: `1px solid ${p.gold}55` }}>
          <Corner className="absolute left-2 top-2 h-10 w-10" color={p.gold} />
          <Corner className="absolute right-2 top-2 h-10 w-10 rotate-90" color={p.gold} />
          <Corner className="absolute bottom-2 left-2 h-10 w-10 -rotate-90" color={p.gold} />
          <Corner className="absolute bottom-2 right-2 h-10 w-10 rotate-180" color={p.gold} />

          <div className="text-center">
            <div
              className="mx-auto flex h-16 w-16 items-center justify-center rounded-full border font-moul text-sm"
              style={{ borderColor: p.gold, color: p.gold }}
            >
              {monogram(groom.primary, bride.primary)}
            </div>
            <p className="mt-5 text-xs tracking-[0.3em]" style={{ color: p.gold }}>
              {L.youAreInvited}
            </p>

            <div className="mt-6">
              <h1 className="font-moul text-2xl sm:text-4xl leading-relaxed" style={{ color: p.gold }}>
                {groom.primary}
              </h1>
              {groom.secondary && <p className="mt-1 text-lg opacity-80">{groom.secondary}</p>}
              {content.groom.parents && <p className="mt-1 text-xs opacity-70">{content.groom.parents}</p>}

              <div className="my-4 text-xl" style={{ color: p.gold }}>
                {L.and}
              </div>

              <h1 className="font-moul text-2xl sm:text-4xl leading-relaxed" style={{ color: p.gold }}>
                {bride.primary}
              </h1>
              {bride.secondary && <p className="mt-1 text-lg opacity-80">{bride.secondary}</p>}
              {content.bride.parents && <p className="mt-1 text-xs opacity-70">{content.bride.parents}</p>}
            </div>

            <p className="mt-6 text-xs tracking-[0.2em] opacity-70">{L.withFamilies}</p>

            {content.rsvpEnabled && (
              <a
                href="#rsvp"
                className="mt-6 inline-block rounded-full px-6 py-2 text-sm"
                style={{ backgroundColor: p.gold, color: p.bg }}
              >
                {L.rsvp}
              </a>
            )}
          </div>
        </div>

        {content.coverPhoto && (
          <div className="mt-8 overflow-hidden rounded-lg" style={{ border: `1px solid ${p.gold}55` }}>
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

        <GoldDivider color={p.gold} />

        {/* When & where */}
        <section className="text-center">
          <h2 className="font-moul text-lg" style={{ color: p.gold }}>
            {L.when}
          </h2>
          {dp ? (
            <div className="mt-3">
              <p className="text-sm opacity-80">{dp.weekday}</p>
              <p className="mt-1 text-3xl" style={{ color: p.gold }}>
                {dp.day} {dp.month} {dp.year}
              </p>
              {timeStr && <p className="mt-1 opacity-80">{timeStr}</p>}
              {content.event.lunarNote && (
                <p className="mt-2 text-sm" style={{ color: p.gold }}>
                  {content.event.lunarNote}
                </p>
              )}
            </div>
          ) : (
            <p className="mt-3 opacity-50">—</p>
          )}

          <div className="mt-6">
            <Countdown target={eventDateTime(content)} labels={L.countdown} />
          </div>
        </section>

        {(content.event.venueName || mapEmbed) && (
          <section className="mt-10 text-center">
            <h2 className="font-moul text-lg" style={{ color: p.gold }}>
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
                  style={{ borderColor: p.gold, color: p.gold }}
                >
                  {L.addToCalendar}
                </a>
              )}
              {content.event.mapUrl && (
                <a
                  href={content.event.mapUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-full px-5 py-2 text-sm"
                  style={{ backgroundColor: p.gold, color: p.bg }}
                >
                  {L.getDirections}
                </a>
              )}
            </div>
            {mapEmbed && (
              <div className="mt-5 overflow-hidden rounded" style={{ border: `1px solid ${p.gold}55` }}>
                <iframe title="map" src={mapEmbed} className="h-64 w-full" loading="lazy" />
              </div>
            )}
          </section>
        )}

        {content.loveStory && (
          <section className="mt-10 text-center">
            <GoldDivider color={p.gold} />
            <h2 className="font-moul text-lg" style={{ color: p.gold }}>
              {L.ourStory}
            </h2>
            <p className="mx-auto mt-3 max-w-prose leading-loose opacity-90">{content.loveStory}</p>
          </section>
        )}

        {content.photos.length > 0 && (
          <section className="mt-10 grid grid-cols-2 gap-3 sm:grid-cols-3">
            {content.photos.map((src, i) => (
              <div
                key={i}
                className="aspect-square overflow-hidden rounded"
                style={{ border: `1px solid ${p.gold}55` }}
              >
                <Image src={src} alt="" width={600} height={600} className="h-full w-full object-cover" />
              </div>
            ))}
          </section>
        )}

        <footer className="mt-12 text-center">
          <GoldDivider color={p.gold} />
          <p className="text-sm" style={{ color: p.gold }}>
            {L.thankYou}
          </p>
          <p className="mt-2 font-moul text-lg" style={{ color: p.gold }}>
            {groom.primary} {L.and} {bride.primary}
          </p>
          {content.hashtag && (
            <p className="mt-2 text-xs tracking-widest opacity-60">#{content.hashtag.replace(/^#/, '')}</p>
          )}
        </footer>
      </div>

      {content.musicUrl && <BackgroundMusic src={content.musicUrl} color={p.gold} />}
    </div>
  );
}
