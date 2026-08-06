# Contributing to Godena

Godena gets better when the network grows and the data stays honest. There are three ways to help — pick whichever fits.

## 1. Add an agent (no code)

**Over WhatsApp:** text `+256761966728`, reply `2`, and follow the steps.

**Over the API:**

```bash
curl -X POST https://sammygh-godena.hf.space/api/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Grace_Legal_Nairobi",
    "skill": "legal",
    "location": "nairobi",
    "country": "kenya",
    "whatsapp": "https://wa.me/254712345678"
  }'
```

## 2. Improve the core (code)

1. Fork the repo and create a branch.
2. Make your change. Keep it focused and readable.
3. Open a pull request describing what and why.

Good first contributions: new skill synonyms, new city/location words, search-quality fixes, verification/“check” logic, and the post-introduction rating step.

## The one hard rule: no fake data

This is what makes Godena trustworthy, so it is not optional.

- **Never invent a contact, a rating, or an agent.** A wrong number does more damage than an empty result.
- **Named brands** (airlines, banks, telcos) may only be listed with their **real, official, publicly verifiable** contact. If it is not confirmed official, mark it clearly as unofficial/public info or leave it out.
- **No seeding fake reputation** (fake reviews, fake jobs, fake endorsements). Reputation must be earned.

PRs that add unverified or fabricated data will be rejected.

## Run it locally

- Python 3.12, FastAPI. Install: `pip install -r requirements.txt`.
- Put secrets in a local `.env` (git-ignored) — Supabase, Green API, Telegram. **Never commit secrets.** See [SECURITY.md](SECURITY.md).
- Run: `python app.py` (serves on port 7860).

## Fork a city

Want a Lagos or Addis or diaspora network? Fork it, point it at your own Supabase, set your own WhatsApp/Telegram secrets in your Hugging Face Space, and seed your own agents. Same code, different registry. Reach out if you want city networks to federate.
