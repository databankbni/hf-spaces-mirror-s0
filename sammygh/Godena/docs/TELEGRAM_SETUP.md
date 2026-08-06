# Go live on Telegram in 5 minutes (no phone number needed)

Telegram bots need **zero** phone number and cost **nothing**. This is Godena's fastest real messaging channel.

## Steps

1. **Create the bot** — in Telegram, message **[@BotFather](https://t.me/BotFather)**:
   - Send `/newbot`
   - Name: `Godena`
   - Username: `GodenaBot` (or `Godena_<something>Bot` if taken)
   - BotFather replies with a **token** like `8459332496:AAH...`. Copy it.
   - *(If a Godena bot already exists: send `/mybots` → pick it → API Token.)*

2. **Give the app the token** — on the Hugging Face Space
   ([huggingface.co/spaces/sammygh/godena](https://huggingface.co/spaces/sammygh/godena) → **Settings → Variables and secrets → New secret**):
   - Name: `TELEGRAM_TOKEN`
   - Value: *(the token from step 1)*
   - Save. The Space restarts automatically.
   *(Or paste the token to Claude and it sets this for you if you provide an HF token.)*

3. **Register the webhook** — one call (Claude can run this, or you can):
   ```
   curl "https://api.telegram.org/bot<TELEGRAM_TOKEN>/setWebhook?url=https://sammygh-godena.hf.space/telegram"
   ```
   Expect `{"ok":true,"result":true,"description":"Webhook was set"}`.

4. **Test it** — open your bot in Telegram, send `ai coding`. It should reply with 3 agents (Anthropic, OpenAI, …). Try `lawyer kampala`, `flights nairobi`.

That's it — Godena is live on Telegram, no number, no cost. Share the `t.me/YourBot` link anywhere.

## Notes
- The bot serves the same engine and the 138-agent embedded snapshot, so it works even while the Supabase database is paused.
- To later add WhatsApp without owning a number, use the **Twilio WhatsApp Sandbox** (shared number, users send a join code) for demos, then a verified business number at scale.
