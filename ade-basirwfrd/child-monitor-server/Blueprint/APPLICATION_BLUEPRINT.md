# Blueprint Lengkap — Child Monitor (Judol / Parental Monitoring)

Dokumen ini menjelaskan **implementasi aktual** di repositori ini (April 2026), bukan desain generik. Untuk sejarah atau contoh kode lama, lihat `blueprint.md` (catatan: file tersebut sebagian sudah tidak selaras dengan kode saat ini).

---

## 1. Ringkasan pemahaman

**Sistem ini** adalah solusi **pemantauan perangkat anak di Android** yang menggabungkan:

- **Aplikasi anak (`ChildMonitor`)**: berjalan sebagai layanan latar (foreground service), memantau aplikasi foreground, URL browser lewat aksesibilitas, status VPN, mengirim log dan heartbeat ke server, menerima perintah **Firebase Cloud Messaging (FCM)**, dan dapat **mengunci layar** lewat Device Admin serta mode **kuis penguncian** (`QuizActivity`).
- **Backend Node.js (`backend/`)**: API REST Express, integrasi **Supabase** sebagai database, **Firebase Admin** untuk push ke perangkat, **email Brevo** untuk alert ke orang tua, filter judi/blokir URL, cron pengecekan perangkat “stale”, dan **dashboard web statis** di `public/`.
- **Aplikasi orang tua (`ParentMonitor`)**: shell **WebView** yang membuka URL dashboard backend (setelah konfigurasi `server_url`).

Alur inti: perangkat anak mengirim aktivitas → server menyimpan & menganalisis URL → jika terblokir/diduga judi, kirim **email alert** + **FCM `block`** → di perangkat, jika VPN tidak aktif, perintah blok dapat memicu **kunci layar**.

---

## 2. Tujuan fungsional

| Area | Perilaku |
|------|----------|
| Pelacakan aplikasi | `UsageStatsMonitor` + `MainService` (~setiap 2 detik) mendeteksi perubahan aplikasi foreground dan mengirim log. |
| Pelacakan web | `URLMonitoringService` (Accessibility) membaca URL dari browser; log dikirim ke server. |
| Deteksi judi / blokir | Server: `checkUrlBlock()` — domain list + keyword host/path. Client: `JudiFilter` + sinkron blocklist dari API. |
| Orang tua | Email (Brevo), dashboard web, opsional app Parent WebView. |
| Kontrol jarak jauh | FCM: `lock`, `block`, `update_blocklist`, `start_quiz`, `stop_quiz`, `restart`. |
| Ketahanan | Heartbeat, registrasi berkala, interceptor 401 memicu **auto-register** (“self-healing”). |

---

## 3. Arsitektur (tingkat tinggi)

```
┌─────────────────────────────┐     HTTPS REST      ┌──────────────────────────────┐
│  Android — ChildMonitor      │ ◄──────────────────►│  Backend (Express)           │
│  MainService, URL A11y,      │                     │  routes/api.js, index.js     │
│  MyVpnService, FCM, DPM      │                     │  fcm.js, emailNotifier.js    │
│  Room + Retrofit             │                     │  judiFilter.js, models/db.js │
└─────────────────────────────┘                     └──────────────┬───────────────┘
         │ FCM push                                                │
         ▼                                                           ▼
┌─────────────────┐                                      ┌─────────────────┐
│ Firebase Cloud  │                                      │ Supabase (PG)   │
│ Messaging       │                                      │ devices, logs,  │
└─────────────────┘                                      │ blocklist,      │
                                                         │ error_logs      │
                                                         └─────────────────┘
         Email alerts
                ▼
┌─────────────────┐
│ Brevo SMTP API  │
└─────────────────┘

Orang tua: browser atau ParentMonitor (WebView) → static dashboard di /public
```

---

## 4. Backend (`backend/`)

### 4.1 Teknologi

- **Runtime**: Node.js  
- **Framework**: Express (`index.js`, `routes/api.js`)  
- **Database**: **Supabase** (`@supabase/supabase-js`) — klien di `models/db.js`  
- **Push**: `firebase-admin` (`services/fcm.js`)  
- **Email**: Brevo HTTP API (`services/emailNotifier.js`) + `node-fetch`  
- **Jadwal**: `node-cron` (heartbeat stale, per jam)  
- **Static**: `express.static` → `public/` (dashboard HTML)

**Deployment**: README menyebut Hugging Face Space (Docker), port default `PORT` atau 3000.

### 4.2 Skema data (inferensi dari kode)

| Tabel / koleksi | Kolom utama (dari penggunaan kode) |
|-----------------|-----------------------------------|
| `devices` | `device_id` (unik), `wa_number`, `fcm_token`, `last_heartbeat`, `created_at` |
| `logs` | `device_id`, `package_name`, `app_name`, `url`, `timestamp`, `is_judi`, (opsional `sent_wa`) |
| `blocklist` | `domain`, `added_at` |
| `error_logs` | `device_id`, `error_type`, `error_message`, `stack_trace`, `component`, `timestamp` |

Seed awal domain: `judi-domains.json` dipanggil dari `seedBlocklist()` di `db.js`.

### 4.3 Endpoint API (aktual)

Base path: `/api` (kecuali `/api/health` dan beberapa route di root dari `index.js`).

| Metode | Path | Fungsi |
|--------|------|--------|
| POST | `/api/register` | Upsert device: `deviceId`, `waNumber`, `fcmToken` |
| POST | `/api/log` | Log aktivitas; cek blokir URL; 401 jika device tidak terdaftar (self-healing trigger di client) |
| GET | `/api/blocklist` | Domain + keyword + version |
| POST | `/api/blocklist` | Tambah domain |
| DELETE | `/api/blocklist/:domain` | Hapus domain |
| POST | `/api/heartbeat` | Update `last_heartbeat` |
| POST | `/api/alert/service-disabled` | Email: layanan dimatikan |
| POST | `/api/alert/vpn-detected` | Email: VPN aktif di perangkat anak |
| GET | `/api/devices` | Daftar perangkat |
| GET | `/api/logs/:deviceId` | Log per perangkat |
| GET | `/api/error-logs/:deviceId?` | Error log |
| POST | `/api/error-log` | Terima error dari client |
| POST | `/api/quiz/start` | FCM `start_quiz` |
| POST | `/api/quiz/stop` | FCM `stop_quiz` |
| POST | `/api/restart` | **Dimaksudkan** mengirim FCM restart (lihat §9) |
| GET | `/api/status` | Status online + FCM initialized |
| POST | `/api/lock` | Di `index.js`: kunci via `sendLockCommand` |

Di `index.js` juga: `GET /api/health`, `POST /api/lock` (duplikasi pola lock), static files.

### 4.4 Logika bisnis penting — `POST /api/log`

1. Parse body; jika ada `url`, panggil `checkUrlBlock(url)` (domain DB + keyword).  
2. **Cek device terdaftar** — jika tidak, balas **401** + `DEVICE_NOT_REGISTERED` (memicu registrasi ulang di Android).  
3. Simpan log dengan flag judi sesuai hasil cek.  
4. Jika terblokir: email alert + `sendFCM(deviceId, 'block', { url })`.  
5. Jika tidak terblokir tapi ada URL: email info aktivitas web.  

**Catatan**: Parameter `wa_number` di DB tetap disimpan, tetapi **`emailNotifier` memakai alamat email target yang dikode di server** (bukan routing dinamis per `wa_number` untuk setiap email). Sesuaikan jika multi-orang-tua diperlukan.

### 4.5 Filter judi (`utils/judiFilter.js`)

- Cache domain dari Supabase (TTL ~1 menit).  
- Cocokkan hostname: exact, subdomain, keyword di host, keyword di path.  
- Keyword mencakup istilah judi/slot dan sejenisnya (lihat `JUDI_KEYWORDS` di file).

### 4.6 FCM (`services/fcm.js`)

- Inisialisasi dari env `FIREBASE_SERVICE_ACCOUNT` (JSON atau base64) atau `serviceAccountKey.json`.  
- `sendFCM(deviceId, command, extraData)` — selalu resolve token lewat `getDeviceById(deviceId)`.

Perintah yang ditangani di Android termasuk: `lock`, `block`, `update_blocklist`, `start_quiz`, `stop_quiz`, `restart`.

### 4.7 Cron

Setiap jam: `getStaleDevices(threshold)` dengan threshold 24 jam → email peringatan perangkat offline.

---

## 5. Dashboard web (`backend/public/`)

- SPA/HTML tunggal (`index.html`) dengan UI gelap (Inter, Material Icons), PWA manifest (`manifest.json`).  
- Mengonsumsi API backend yang sama (devices, logs, lock, quiz, dll. — sesuai implementasi JS di halaman).

---

## 6. Android — ChildMonitor (`android/ChildMonitor/`)

### 6.1 Paket & konfigurasi

- Package: `com.example.childmonitor`  
- **Retrofit** base URL default: Hugging Face Space (lihat `RetrofitClient.DEFAULT_URL`); bisa diubah di `SetupActivity` → disimpan `SharedPreferences` `server_url`.  
- **Firebase**: `google-services.json` ada di proyek.

### 6.2 Komponen utama

| Komponen | Peran |
|----------|--------|
| `SetupActivity` | Input `wa_number` (kontak/label), `server_url`, `device_id`/`device_name`; minta izin usage stats, battery, device admin, dsb.; registrasi FCM. |
| `MainService` | Foreground service; pemantauan app; `JudiFilter.syncBlocklist`; heartbeat (~2 menit); auto-registration (~5 menit); deteksi VPN. |
| `UsageStatsMonitor` | App foreground. |
| `URLMonitoringService` | Accessibility — URL browser. |
| `MyVpnService` | VPN lokal untuk blokir domain (sesuai implementasi). |
| `MyFirebaseMessagingService` | Handle perintah FCM (lock, block, quiz, restart, update blocklist). |
| `AdminReceiver` | Device admin — `lockNow`. |
| `QuizActivity` | Mode kuis / lockdown UI. |
| `BootReceiver` | Start service setelah boot/update. |
| `JudiFilter` | Filter lokal + sync server blocklist. |
| `LogSenderWorker` / `RegistrationWorker` / `ErrorReporter` | Pengiriman log/error/pekerjaan latar. |
| Room (`AppDatabase`, `LogDao`, …) | Buffer log offline. |

### 6.3 Self-healing

`RetrofitClient` interceptor pada **HTTP 401** mem-start `MainService` dengan `ACTION_AUTO_REGISTER` untuk registrasi ulang.

### 6.4 ParentMonitor (`android/ParentMonitor/`)

- `SetupActivity`: simpan `server_url`.  
- `MainActivity`: WebView memuat `server_url` (dashboard).  

---

## 7. Variabel lingkungan & rahasia

**Yang diharapkan untuk produksi:**

- `PORT`  
- `FIREBASE_SERVICE_ACCOUNT` (JSON string atau base64)  
- **Supabase**: sebaiknya `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` (saat ini ada di `models/db.js` — **risiko keamanan** jika repo publik).  
- **Brevo**: API key dan email pengirim/penerima sebaiknya env, bukan hardcode.

---

## 8. Etika & kepatuhan

- Aplikasi memakai izin sangat sensitif (usage stats, aksesibilitas, device admin, VPN).  
- Pastikan penggunaan sesuai hukum setempat dan kebijakan toko aplikasi; transparansi kepada pengguna perangkat.  
- Dokumen ini bersifat teknis; tanggung jawab penggunaan ada pada pengembang/pengguna.

---

## 9. Utang teknis / bug yang perlu diketahui

1. **`POST /api/restart`**: memanggil `sendFCM(device.fcm_token, { command: 'restart' })`, padahal `sendFCM` di `fcm.js` mengharapkan **`(deviceId, command)`** dan mengambil token sendiri dari DB. Perlu diperbaiki menjadi `sendFCM(deviceId, 'restart')` agar restart remote berfungsi.  
2. **Rahasia di repo**: kunci Supabase dan Brevo di kode harus dipindah ke env dan key di-rotate jika pernah terpapar.  
3. **`blueprint.md` lama**: menggambarkan WhatsApp bot dan SQLite sebagai inti — **tidak mencerminkan** stack aktual (Supabase + email).

---

## 10. Struktur direktori referensi

```
judol is real/
├── backend/
│   ├── index.js
│   ├── routes/api.js
│   ├── models/db.js
│   ├── services/fcm.js
│   ├── services/emailNotifier.js
│   ├── utils/judiFilter.js
│   ├── judi-domains.json
│   └── public/                 # Dashboard
├── android/
│   ├── ChildMonitor/           # Aplikasi anak
│   └── ParentMonitor/          # WebView orang tua
├── package.json                # Script root: start backend
└── Blueprint/
    ├── APPLICATION_BLUEPRINT.md  # Dokumen ini
    └── blueprint.md              # Dokumen historis / contoh (sebagian outdated)
```

---

## 11. Kesimpulan

Blueprint ini mencakup **arsitektur nyata**, **aliran data**, **modul Android dan backend**, **kontrak API**, **integrasi Supabase, FCM, dan email**, serta **catatan keamanan dan bug**. Dengan ini, implementasi di repositori dapat dipahami sebagai satu kesatuan sistem monitoring parental berbasis log URL/aplikasi, deteksi konten judi, alert email, dan kontrol jarak jauh melalui FCM.
