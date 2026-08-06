---
title: SecurityApp
emoji: 🛡️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# SecurityApp

Enterprise-grade security features built into a Laravel 13 application.

## Features

| # | Feature | Implementation |
|---|---------|---------------|
| 1 | **Strong Passwords** | Auto-generate with uppercase/lowercase/symbols/numbers. Validation rule enforces minimum strength. |
| 2 | **Encryption & Hashing** | AES-256 encryption via Laravel Crypt + bcrypt hashing (BCRYPT_ROUNDS=12). |
| 3 | **TFA / MFA** | Email-based two-factor authentication with recovery codes. Enable/disable from dashboard. |
| 4 | **Activity Logs** | Full audit trail of user actions with IP, user agent, and metadata. |
| 5 | **Max Login Attempts** | Rate-limited login (5 attempts max) with automatic throttling. |
| 6 | **Backup & Restore** | SQLite database backup/restore via web UI or Artisan commands. |
| 7 | **Email Notifications** | Login alerts, TFA codes, and backup status emails. |
| 8 | **OAuth** | Social login via GitHub, Google, Facebook, Twitter, LinkedIn (Laravel Socialite). |

## Quick Start

```bash
cp .env.example .env
php artisan key:generate
php artisan migrate
php artisan serve
```

Browse to `http://localhost:8000` and register an account.

### Artisan Commands

```bash
# Generate strong passwords
php artisan security:generate-password --length=20 --count=5

# Backup database
php artisan security:backup

# Restore from backup
php artisan security:restore --latest
```

## Deploy to Hugging Face Spaces

### Prerequisites
- A [Hugging Face](https://huggingface.co) account
- Git configured with your HF token

### Step-by-Step

1. **Create a new Space:**
   - Go to https://huggingface.co/new-space
   - Enter a Space name (e.g., `securityapp`)
   - Select **Docker** as the Space SDK
   - Click "Create Space"

2. **Add your HF remote and push:**
   ```bash
   git remote add hf https://huggingface.co/spaces/YOUR_USERNAME/securityapp
   git push hf main
   ```

3. **Configure Environment Variables (optional):**
   In your Space Settings → Repository secrets, add:
   - `APP_URL` - Your Space URL
   - `MAIL_MAILER` - Set to `smtp` and configure SMTP credentials for real emails
   - `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` - For GitHub OAuth
   - `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` - For Google OAuth

4. **Wait for build:** The Space will automatically build and deploy. Watch the logs in the "Builder" tab.

Your app will be live at `https://YOUR_USERNAME-securityapp.hf.space`

### Docker Architecture

The deployment uses:
- `php:8.3-fpm` base image
- Nginx as web server (port 7860)
- PHP-FPM for Laravel
- Supervisor to manage both processes
- SQLite database (persists across restarts, fresh on rebuild)
