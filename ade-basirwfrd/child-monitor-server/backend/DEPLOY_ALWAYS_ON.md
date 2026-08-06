# Deploy backend always-on (ganti Hugging Face sleep)

Hugging Face Space gratis sering **idle/hibernate**. Monitoring anak butuh API yang selalu menjawab.

## Opsi A — Fly.io (direkomendasikan)

1. Install CLI: https://fly.io/docs/hands-on/install-flyctl/
2. Login: `fly auth login`
3. Dari root repo: `fly launch` (atau pakai [`fly.toml`](../fly.toml) yang sudah ada) lalu:
   ```bash
   fly secrets set \
     SUPABASE_URL="https://xxxx.supabase.co" \
     SUPABASE_SERVICE_ROLE_KEY="..." \
     BREVO_API_KEY="..." \
     EMAIL_ALERT_TO="parent@example.com" \
     BREVO_SENDER_EMAIL="parent@example.com" \
     PUBLIC_BASE_URL="https://child-monitor-server.fly.dev" \
     FIREBASE_SERVICE_ACCOUNT="$(cat backend/serviceAccountKey.json | jq -c .)"
   fly deploy
   ```
4. Verifikasi: `curl https://YOUR-APP.fly.dev/api/health`
5. Di ChildMonitor: set URL server ke URL Fly, atau biarkan app sync lewat `GET /api/config` setelah `PUBLIC_BASE_URL` benar.
6. Opsional: matikan Space HF atau biarkan sebagai mirror (bukan sumber kebenaran).

## Opsi B — Railway

1. New project dari repo GitHub, root = repo ini.
2. Pakai [`railway.toml`](../railway.toml) (`npm start --prefix backend`).
3. Set variabel sama seperti `.env.example`, termasuk `PUBLIC_BASE_URL=https://YOUR.up.railway.app`.
4. Pastikan `restartPolicy` selalu on (sudah di `railway.toml`).

## Setelah deploy

1. Jalankan SQL opsional: [`sql/devices_health_columns.sql`](sql/devices_health_columns.sql) di Supabase SQL Editor.
2. Update `android/ChildMonitor/gradle.properties`:
   ```
   DEFAULT_SERVER_URL=https://YOUR-ALWAYS-ON-HOST
   ```
3. Rebuild APK anak (`assembleRelease` / `assembleDebug`).
4. Dashboard parent: buka URL always-on (bukan HF).

## Catatan

- `auto_stop_machines = "off"` + `min_machines_running = 1` di Fly mencegah sleep.
- Jangan commit secret / `serviceAccountKey.json`.

## Supabase keep-alive (GitHub Actions)

Supabase **free** bisa **pause** jika lama tidak ada query. Workflow  
[`.github/workflows/supabase-keepalive.yml`](../.github/workflows/supabase-keepalive.yml)  
jalan **setiap hari** (dan bisa dijalankan manual) untuk `GET /rest/v1/devices`.

1. Push repo ke GitHub (jika belum).
2. Repo → **Settings → Secrets and variables → Actions** → tambah:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`
3. **Actions → Supabase keep-alive → Run workflow** (uji sekali).

Ini **hanya** menjaga Supabase. Hugging Face Space sleep = masalah terpisah (pakai always-on host di atas).
