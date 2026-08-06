-- Jalankan sekali di Supabase SQL Editor (project baru).
-- Table Public → SQL → New query → Run

CREATE TABLE IF NOT EXISTS devices (
  id bigserial PRIMARY KEY,
  device_id text UNIQUE NOT NULL,
  wa_number text,
  fcm_token text,
  last_heartbeat bigint,
  created_at bigint,
  is_device_owner boolean DEFAULT false,
  admin_active boolean DEFAULT false,
  service_running boolean DEFAULT true,
  app_version text,
  last_health_at bigint
);

CREATE TABLE IF NOT EXISTS logs (
  id bigserial PRIMARY KEY,
  device_id text,
  package_name text,
  app_name text,
  url text,
  timestamp bigint,
  is_judi integer DEFAULT 0,
  sent_wa integer DEFAULT 0
);

CREATE INDEX IF NOT EXISTS logs_device_ts ON logs (device_id, timestamp DESC);

CREATE TABLE IF NOT EXISTS blocklist (
  domain text PRIMARY KEY,
  added_at bigint
);

CREATE TABLE IF NOT EXISTS error_logs (
  id bigserial PRIMARY KEY,
  device_id text,
  error_type text,
  error_message text,
  stack_trace text,
  component text,
  timestamp bigint
);

CREATE INDEX IF NOT EXISTS error_logs_device_ts ON error_logs (device_id, timestamp DESC);
