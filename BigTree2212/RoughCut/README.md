---
title: AI Tools Studio
emoji: 🎛️
colorFrom: gray
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
---

# AI Tools Studio

Satu website yang menggabungkan tiga tool video lokal:

- **Silence Cutter** (`/silence-cutter`) — buang bagian sunyi dari video secara otomatis.
- **Video Transcript** (`/transcript`) — transkripsi video ke teks per segmen pakai `faster-whisper`.
- **Video Downloader** (`/video-downloader`) — download video/audio dari YouTube, TikTok, atau Instagram pakai `yt-dlp`.

Home (`/`) menampilkan dashboard untuk memilih salah satu tool. Nav bar di
setiap halaman bisa dipakai untuk pindah antar tool atau balik ke home tanpa
buka tab baru. Tiap tool tetap punya URL sendiri jadi bisa langsung di-share.

Ketiga tool berbagi **satu antrian global** (`/queue`) — server hanya
memproses satu job (dari tool manapun) dalam satu waktu, supaya ffmpeg/
whisper/yt-dlp nggak berebut CPU. Progress dan hasil tiap job juga terlihat
oleh siapa saja yang buka halaman itu, bukan cuma yang upload/mulai job-nya.

## Struktur project

```
ai-tools-studio/
├── app.py                     # entrypoint: registers blueprints + home route + /queue
├── queue_manager.py           # antrian global lintas tools (satu job jalan sekaligus)
├── blueprints/
│   ├── silence_cutter/        # /silence-cutter — routes, ffmpeg processor
│   ├── transcript/            # /transcript — routes, faster-whisper worker
│   └── video_downloader/      # /video-downloader — routes, yt-dlp downloader
├── templates/
│   ├── base.html              # shared layout + top nav + confirm modal
│   ├── home.html               # dashboard cards
│   ├── queue.html              # antrian global
│   ├── silence_cutter/index.html
│   ├── transcript/index.html
│   └── video_downloader/index.html
├── static/
│   ├── css/base.css            # design system: colors, fonts, nav, cards, job-card, slot/reel motif
│   ├── css/{silence_cutter,transcript,video_downloader}.css  # tool-specific styles
│   └── js/                     # per-tool client logic + confirm.js + queue.js
├── data/                       # uploads/outputs per tool (gitignored)
├── requirements.txt
└── Dockerfile
```

## Cara jalanin lokal

Butuh **Python 3.10+**, **ffmpeg**, dan `yt-dlp` (dari `pip install -r requirements.txt`) ter-install.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Buka `http://localhost:7860`.

- Model Whisper (`medium` secara default, ~1.5 GB) otomatis di-download ke
  cache Hugging Face saat pertama kali dipakai — butuh internet sekali di awal.
- `ffmpeg`/`ffprobe` dipakai langsung sebagai subprocess oleh Silence Cutter, Transcript, dan Video Downloader.
- Video Downloader butuh koneksi internet setiap kali dipakai (mengambil video dari YouTube/TikTok/Instagram).

## Konfigurasi (environment variable)

| Variabel | Default | Tool | Keterangan |
|---|---|---|---|
| `PORT` | `7860` | semua | Port server Flask |
| `SILENCE_CUTTER_DATA_DIR` | `data/silence_cutter` | Silence Cutter | Lokasi upload & output |
| `TRANSCRIPT_DATA_DIR` | `data/transcript` | Transcript | Lokasi upload, output, `jobs_db.json` |
| `WHISPER_MODEL_SIZE` | `medium` | Transcript | `tiny`/`base`/`small`/`medium`/`large-v3` |
| `WHISPER_DEVICE` | `cpu` | Transcript | `cpu` atau `cuda` |
| `WHISPER_COMPUTE_TYPE` | `int8` | Transcript | Tipe komputasi ctranslate2 |
| `WHISPER_LANGUAGE` | `id` | Transcript | Kosongkan untuk auto-detect |
| `MAX_UPLOAD_MB` | `1024` | Transcript | Batas ukuran upload video |
| `VIDEO_DOWNLOADER_DATA_DIR` | `data/video_downloader` | Video Downloader | Lokasi hasil download & `jobs_db.json` |
| `MAX_FILE_AGE_HOURS` | `24` | Video Downloader | Hasil download lebih tua dari ini otomatis dihapus |
| `CLEANUP_INTERVAL_SECONDS` | `1800` | Video Downloader | Interval pengecekan file lawas |
| `MAX_RETRIES` | `2` | Transcript, Video Downloader | Percobaan ulang otomatis sebelum job gagal permanen |
| `YOUTUBE_COOKIES_B64` | *(kosong)* | Video Downloader | Opsional. Isi `cookies.txt` (format Netscape) dalam base64, di-set sebagai **Space secret**. `start.sh` decode ini jadi file saat container start dan yt-dlp otomatis memakainya bareng PO Token. Lihat bagian Deploy di bawah. |

## Deploy ke Hugging Face Spaces

1. Buat Space baru dengan **SDK: Docker**.
2. Push seluruh isi folder ini (frontmatter di atas README ini sudah berisi
   metadata Space yang dibutuhkan).
3. Space build image, install `ffmpeg` + `bgutil-pot` (binary Rust statis,
   generate PO Token buat yt-dlp menembus proteksi anti-bot YouTube -- tidak
   butuh Node.js/Deno) + dependency Python, lalu jalan di port `7860`.
4. Kalau Space punya persistent storage add-on (mount di `/data`), Silence
   Cutter dan Video Downloader otomatis pakai `/data/silence-cutter` dan
   `/data/video-downloader` supaya tidak kena limit disk ephemeral.
5. **Opsional — kalau YouTube masih menolak sebagian video meski PO Token
   sudah aktif** (biasanya video age-restricted atau yang butuh sesi login),
   tambahkan cookies YouTube sebagai lapisan kedua:
   - Login ke akun Google **cadangan** (bukan akun utama -- akun ini
     berisiko kena flag dari pola akses otomatis) di browser, lalu export
     cookies pakai extension seperti "Get cookies.txt LOCALLY" ke format
     Netscape (`cookies.txt`).
   - Encode ke base64 satu baris: `base64 -i cookies.txt | tr -d '\n'`
   - Di Space **Settings → Variables and secrets → New secret** (bukan
     "New variable" -- secret terenkripsi dan cuma ter-inject sebagai env
     var ke container yang jalan), buat secret bernama `YOUTUBE_COOKIES_B64`
     berisi string base64 tadi.
   - Jangan pernah commit `cookies.txt` atau base64-nya ke repo. Cookies ini
     juga akan expire seiring waktu (logout, 2FA, dll) -- perlu di-refresh
     berkala kalau video yang butuh login mulai gagal lagi.
