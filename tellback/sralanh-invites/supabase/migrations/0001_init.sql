-- ===========================================================================
-- SraLanh Invites — initial schema
-- Apply via Supabase SQL editor or `supabase db push`.
-- ===========================================================================

create extension if not exists "pgcrypto"; -- gen_random_uuid()

-- --- enums ------------------------------------------------------------------
do $$ begin
  create type user_role as enum ('buyer', 'admin');
exception when duplicate_object then null; end $$;

do $$ begin
  create type tier as enum ('basic', 'premium');
exception when duplicate_object then null; end $$;

do $$ begin
  create type payment_status as enum ('pending', 'paid', 'failed', 'refunded');
exception when duplicate_object then null; end $$;

do $$ begin
  create type invite_status as enum ('draft', 'published', 'expired');
exception when duplicate_object then null; end $$;

do $$ begin
  create type design_request_status as enum ('requested', 'in_progress', 'delivered');
exception when duplicate_object then null; end $$;

-- --- users (profile row mirrors auth.users) ---------------------------------
create table if not exists public.users (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  name text,
  role user_role not null default 'buyer',
  locale_pref text default 'en',
  created_at timestamptz not null default now()
);

-- --- templates --------------------------------------------------------------
create table if not exists public.templates (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  slug text not null unique,
  description text,
  tags text[] default '{}',
  preview_images text[] default '{}',
  base_price numeric(10,2) not null default 0,
  tier tier not null default 'basic',
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

-- --- orders -----------------------------------------------------------------
create table if not exists public.orders (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.users(id) on delete set null,
  template_id uuid references public.templates(id) on delete set null,
  template_slug text,                       -- denormalised for convenience
  tier_purchased tier not null default 'basic',
  amount numeric(10,2) not null default 0,
  currency text not null default 'usd',
  payment_provider text not null default 'stripe',
  payment_ref text,                         -- provider session/tran id
  payment_status payment_status not null default 'pending',
  created_at timestamptz not null default now()
);
create index if not exists orders_user_id_idx on public.orders(user_id);
create index if not exists orders_payment_ref_idx on public.orders(payment_ref);

-- --- invites ----------------------------------------------------------------
create table if not exists public.invites (
  id uuid primary key default gen_random_uuid(),
  order_id uuid references public.orders(id) on delete cascade,
  slug text not null unique,                -- /invite/<slug>
  subdomain text unique,                    -- premium custom subdomain
  status invite_status not null default 'draft',
  content_json jsonb not null default '{}'::jsonb,
  hosting_expires_at timestamptz,           -- recurring hosting model
  custom_domain_expires_at timestamptz,
  published_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists invites_order_id_idx on public.invites(order_id);

-- --- rsvps (Premium — endpoint stubbed for MVP) -----------------------------
create table if not exists public.rsvps (
  id uuid primary key default gen_random_uuid(),
  invite_id uuid not null references public.invites(id) on delete cascade,
  guest_name text not null,
  attending boolean not null default true,
  guest_count int not null default 1,
  meal_pref text,
  note text,
  created_at timestamptz not null default now()
);
create index if not exists rsvps_invite_id_idx on public.rsvps(invite_id);

-- --- guestbook (Premium — endpoint stubbed for MVP) -------------------------
create table if not exists public.guestbook_entries (
  id uuid primary key default gen_random_uuid(),
  invite_id uuid not null references public.invites(id) on delete cascade,
  name text not null,
  message text not null,
  created_at timestamptz not null default now()
);
create index if not exists guestbook_invite_id_idx on public.guestbook_entries(invite_id);

-- --- custom design requests (manual fulfilment queue) -----------------------
create table if not exists public.custom_design_requests (
  id uuid primary key default gen_random_uuid(),
  order_id uuid references public.orders(id) on delete cascade,
  brief_text text,
  reference_images text[] default '{}',
  status design_request_status not null default 'requested',
  assigned_to text,
  created_at timestamptz not null default now()
);

-- --- webhook idempotency ----------------------------------------------------
-- One row per processed payment webhook event; PK makes double-delivery a no-op.
create table if not exists public.processed_webhook_events (
  event_id text primary key,
  provider text not null,
  processed_at timestamptz not null default now()
);

-- --- updated_at trigger for invites -----------------------------------------
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end $$;

drop trigger if exists invites_set_updated_at on public.invites;
create trigger invites_set_updated_at
  before update on public.invites
  for each row execute function public.set_updated_at();

-- ===========================================================================
-- Row Level Security
-- Server-side privileged work (order fulfilment, invite creation, webhooks)
-- uses the SERVICE ROLE key, which bypasses RLS. These policies govern the
-- browser (anon key) surface only.
-- ===========================================================================
alter table public.users enable row level security;
alter table public.templates enable row level security;
alter table public.orders enable row level security;
alter table public.invites enable row level security;
alter table public.rsvps enable row level security;
alter table public.guestbook_entries enable row level security;
alter table public.custom_design_requests enable row level security;
alter table public.processed_webhook_events enable row level security; -- no anon policies -> locked

-- templates: anyone can read active templates
drop policy if exists templates_read_active on public.templates;
create policy templates_read_active on public.templates
  for select using (is_active = true);

-- users: a user can see/update only their own profile row
drop policy if exists users_self_select on public.users;
create policy users_self_select on public.users
  for select using (auth.uid() = id);
drop policy if exists users_self_update on public.users;
create policy users_self_update on public.users
  for update using (auth.uid() = id);

-- orders: buyer can read their own orders
drop policy if exists orders_owner_select on public.orders;
create policy orders_owner_select on public.orders
  for select using (auth.uid() = user_id);

-- invites: PUBLIC can read PUBLISHED invites (guests opening the link);
-- owners (via the order) can read/update their own drafts.
drop policy if exists invites_public_read on public.invites;
create policy invites_public_read on public.invites
  for select using (
    status = 'published'
    or exists (
      select 1 from public.orders o
      where o.id = invites.order_id and o.user_id = auth.uid()
    )
  );
drop policy if exists invites_owner_update on public.invites;
create policy invites_owner_update on public.invites
  for update using (
    exists (
      select 1 from public.orders o
      where o.id = invites.order_id and o.user_id = auth.uid()
    )
  );

-- rsvps: anyone can INSERT (guests submitting), owner can read.
-- (Rate limiting is enforced at the API layer.)
drop policy if exists rsvps_public_insert on public.rsvps;
create policy rsvps_public_insert on public.rsvps
  for insert with check (true);
drop policy if exists rsvps_owner_read on public.rsvps;
create policy rsvps_owner_read on public.rsvps
  for select using (
    exists (
      select 1 from public.invites i
      join public.orders o on o.id = i.order_id
      where i.id = rsvps.invite_id and o.user_id = auth.uid()
    )
  );

-- guestbook: anyone can INSERT and READ published invites' entries.
drop policy if exists guestbook_public_insert on public.guestbook_entries;
create policy guestbook_public_insert on public.guestbook_entries
  for insert with check (true);
drop policy if exists guestbook_public_read on public.guestbook_entries;
create policy guestbook_public_read on public.guestbook_entries
  for select using (true);

-- ===========================================================================
-- Seed the three starter templates (matches src/data/templates.ts)
-- ===========================================================================
insert into public.templates (name, slug, description, tags, base_price, tier, is_active)
values
  ('Modern Minimalist', 'modern-minimalist',
   'Clean, neutral and elegant — local and international.',
   array['modern','minimalist','neutral','bilingual'], 12, 'basic', true),
  ('Traditional Khmer', 'traditional-khmer',
   'Gold and deep-red royal palette with Angkor-motif borders and Muol headings.',
   array['traditional','khmer','gold','royal'], 15, 'basic', true),
  ('Floral Romantic', 'floral-romantic',
   'Soft pastel palette with illustrated floral corners.',
   array['floral','pastel','romantic','international'], 12, 'basic', true)
on conflict (slug) do nothing;
