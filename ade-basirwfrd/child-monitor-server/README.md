---
title: Child Monitor Server
emoji: 🌖
colorFrom: blue
colorTo: green
sdk: docker
pinned: false
license: mit
---

# Child Monitor Server

Backend Node.js untuk Child Monitoring. **Produksi: host always-on (Fly.io / Railway)** — lihat [`backend/DEPLOY_ALWAYS_ON.md`](backend/DEPLOY_ALWAYS_ON.md). Hugging Face Space gratis sering sleep dan memutus monitoring.

Device Owner / MDM enrollment: [`Blueprint/DEVICE_OWNER_ENROLLMENT.md`](Blueprint/DEVICE_OWNER_ENROLLMENT.md).

## Environment Variables

Set di panel Fly/Railway (atau copy `backend/.env.example` → `backend/.env`).

| Variable | Description |
|----------|-------------|
| `PORT` | Server port (default 3000; Hugging Face often uses 7860) |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role key (or `SUPABASE_SERVICE_KEY`) |
| `BREVO_API_KEY` | Brevo / Sendinblue API key |
| `EMAIL_ALERT_TO` | Email penerima alert (alias: `ALERT_TARGET_EMAIL`) |
| `BREVO_SENDER_EMAIL` | Alamat pengirim (terverifikasi di Brevo); default mengikuti `EMAIL_ALERT_TO` jika kosong |
| `BREVO_SENDER_NAME` | Nama pengirim (opsional) |
| `FIREBASE_SERVICE_ACCOUNT` | JSON service account Firebase (string atau base64), untuk FCM |
| `PUBLIC_BASE_URL` | URL backend tanpa slash akhir; dipakai app lewat `GET /api/config` agar URL di HP selaras dengan server |

## Local Setup
1. `cd backend`
2. `cp .env.example .env` lalu isi kunci (atau gunakan file `.env` yang sudah ada)
3. `npm install`
4. `npm start`

## Supabase keep-alive (GitHub Actions)

Agar project Supabase gratis tidak auto-pause: workflow cron **setiap hari**  
(`.github/workflows/supabase-keepalive.yml`). Set secret `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` di GitHub Actions. Detail: `backend/DEPLOY_ALWAYS_ON.md`.

## ChildMonitor di HP anak (tanpa USB / tanpa ikon di launcher)

Aplikasi tetap **tidak muncul di drawer** setelah memasang APK **release**. Untuk membuka layar setup / menyambungkan ulang:

1. **Halaman pembantu (paling andal di browser HP):** buka **salah satu** URL ini di Space Anda (ganti domain jika beda):
   - `https://<SPACE-ANDA>/open-child-setup.html`
   - `https://<SPACE-ANDA>/open-child-monitor-setup.html` (alias nama panjang)
   - `https://<SPACE-ANDA>/setup-child` (pendek)
2. **Kode di aplikasi Telepon:** `*#*#818181#*#*` — di Samsung sering **tidak** jalan untuk app pihak ketiga.
3. **Jangan** mengetik `childmonitor://` di Chrome (biasanya diblokir). Pakai tombol **intent** di halaman (1).

Isi **URL server**, **ID perangkat**, dan email orang tua di layar setup, lalu simpan.
