# Security policy

## Reporting a vulnerability

If you find a security issue, please **do not open a public issue**. Contact the maintainers privately via Telegram [@GodenaBot](https://t.me/GodenaBot) or the WhatsApp line (+256761966728) and we will respond as quickly as we can.

## Secrets

Godena keeps **all** credentials in environment variables — Supabase keys, Green API token, Telegram token. They are never committed to the repository.

- Never hardcode a token, key, or password in `app.py` or any file.
- For deployment, set secrets in your Hugging Face Space settings (Settings → Variables and secrets).
- Local development: use a `.env` file, which is git-ignored. Never commit it.
- If a secret is ever exposed (a paste, a screenshot, a synced file), **rotate it at the provider** — exposed keys cannot be un-exposed.

## Data

Godena stores public business/agent listings and the phone numbers people use to register. We do not sell user data. Searches are used in aggregate only, to find demand gaps (what people look for that has no agent yet). Treat every stored contact as personal data and handle it accordingly.
