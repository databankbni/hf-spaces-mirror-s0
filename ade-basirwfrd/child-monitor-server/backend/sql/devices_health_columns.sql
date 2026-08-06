-- Jalankan di Supabase SQL Editor (sekali). Kolom opsional untuk Device Owner / kesehatan app.
ALTER TABLE devices ADD COLUMN IF NOT EXISTS is_device_owner boolean DEFAULT false;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS admin_active boolean DEFAULT false;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS service_running boolean DEFAULT true;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS app_version text;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS last_health_at bigint;
