---
title: SraLanh Invites
emoji: 💌
colorFrom: red
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Bilingual Khmer/English wedding invitation marketplace
---

# SraLanh Invites

A marketplace where couples buy customizable digital **wedding invitation
website templates**, personalize them (names, date, venue, photos, RSVP), and
publish a live shareable invite page. Built for **Cambodia (Khmer)** and
**international** buyers.

- **Frontend:** Next.js 14 (App Router) · TypeScript · Tailwind CSS · `output: 'standalone'`
- **Backend:** Supabase (Postgres · Auth · Storage)
- **Payments:** Stripe (live) + ABA PayWay / Bakong adapters (stubbed behind a provider interface)
- **i18n:** next-intl — Khmer (`km`) + English (`en`) as first-class locales
- **Hosting:** Hugging Face Spaces (Docker SDK, port 7860)

> The metadata block at the top of this file is **required** by Hugging Face
> Spaces. `sdk: docker` + `app_port: 7860` tell the Space to build the
> `Dockerfile` and serve the container on port 7860.

---

## Local development

```bash
npm install
cp .env.example .env.local   # then fill in Supabase + Stripe values
npm run dev                  # http://localhost:7860
```

Apply the database schema (either paste `supabase/migrations/0001_init.sql`
into the Supabase SQL editor, or use the Supabase CLI):

```bash
supabase db push
```

Create a public Storage bucket named `invite-photos` (or whatever you set in
`NEXT_PUBLIC_SUPABASE_PHOTOS_BUCKET`).

## Deploying to Hugging Face Spaces

1. Create a **new Space** → SDK = **Docker**.
2. In **Settings → Variables and secrets**, add:
   - **Variables** (public — inlined into the client bundle at build time, so they
     must be Variables, not Secrets): `NEXT_PUBLIC_SITE_URL`,
     `NEXT_PUBLIC_ROOT_DOMAIN`, `NEXT_PUBLIC_SUPABASE_URL`,
     `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_SUPABASE_PHOTOS_BUCKET`,
     `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY`, `PAYMENT_PROVIDER`.
   - **Secrets** (runtime-only, never in the client bundle): `SUPABASE_SERVICE_ROLE_KEY`,
     `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`.
   > HF passes **Variables** to the Docker build as `--build-arg` (see the
   > `ARG NEXT_PUBLIC_*` lines in the Dockerfile), which is how they get inlined.
   > Changing any Variable/Secret triggers a rebuild.
3. Push this repo to the Space:
   ```bash
   git remote add space https://huggingface.co/spaces/<username>/<spacename>
   git push space main
   ```
4. Set `NEXT_PUBLIC_SITE_URL` to `https://<username>-<spacename>.hf.space`.
5. In the **Stripe Dashboard → Developers → Webhooks**, add the endpoint
   `https://<username>-<spacename>.hf.space/api/webhooks/stripe` and copy its
   signing secret into `STRIPE_WEBHOOK_SECRET`.

### ⚠️ Before taking real payments

The **free** Space tier **sleeps after inactivity**. A sleeping container will
break Stripe checkout redirects and make live invite pages unreliable for guests
opening links at random times. **Upgrade to a persistent/paid Space tier before
accepting real customer payments.**

---

## Project layout

```
src/
  app/
    (main)/[locale]/        # localized marketplace (gallery, editor, checkout, dashboards)
    (invite)/invite/[slug]/ # PUBLIC invite pages — locale-agnostic, shareable links
    api/                    # checkout, Stripe webhook, autosave, RSVP/guestbook stubs
  templates/                # invite theme components (content JSON -> rendered invite)
  components/               # gallery cards, editor form, live preview, locale switcher
  lib/
    supabase/               # browser + server clients
    payments/               # PaymentProvider interface + Stripe / ABA / Bakong adapters
    slug.ts, image-compress.ts, rate-limit.ts
  data/                     # template registry metadata + mock invite content
messages/                   # en.json, km.json (next-intl)
supabase/migrations/        # SQL schema
```

## What's implemented vs TODO

**Done:** scaffold + i18n (km/en); Docker/HF metadata; DB schema (migrations
`0001`/`0002`); **all three templates** (Modern Minimalist, Traditional Khmer,
Floral Romantic); template gallery; customization editor with live preview,
autosave and client-side photo compression; **Basic + Premium tiers** (Premium
unlocks RSVP, guestbook, music, custom subdomain); Stripe checkout (test) →
order + draft invite; idempotent webhook; public invite page at `/invite/[slug]`
with auto Open Graph image, **public RSVP form + guestbook wall**; Supabase
**magic-link auth**; **buyer dashboard** (invites, statuses, RSVP counts) and
**admin dashboard** (revenue by template, invite stats, custom-design queue).

**Still `TODO`:** real ABA PayWay / Bakong adapters; require `payment_status =
'paid'` before publish; admin template-upload UI; gallery filters; hosting-renewal
billing + custom-domain DNS provisioning; Khmer webfont in the OG image.
