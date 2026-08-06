# Project: WhatsApp-Telegram Bot

## Stack
- **Runtime**: Node.js 22, pnpm v10, Docker
- **WhatsApp**: `whatsapp-web.js` (Puppeteer + Chrome)
- **Telegram**: `@mtproto/core` (MTProto, **NOT** Bot API)
- **Server**: Express on port 7860 (health check)
- **Storage**: `/data/` directory for sessions

## File Structure
- `index.js` — main app
- `invoice.js` — invoice image generation (Puppeteer HTML→PNG)
- `Dockerfile` — build config (node:22-slim, Chrome, pnpm@10)
- `package.json` — dependencies
- `pnpm-lock.yaml` — lockfile (pnpm v10, lockfileVersion 9.0)
- `pnpm-workspace.yaml` — workspace config
- `AGENTS.md` — this file, read before any edit
- `memory.md` — session context and decisions

## Connection Architecture
```
WhatsApp (user) → whatsapp-web.js (Puppeteer/Chrome) → index.js → @mtproto/core → Telegram (admin)
Telegram (admin) → @mtproto/core → index.js → WhatsApp → WhatsApp (user)
```

## Telegram Methods (MTProto)
All `mtproto.call()` calls MUST pass `{ dcId: 1 }` (number) as 3rd arg to avoid `defaultDcId` string bug.

### Available Libraries
The library (`@mtproto/core`) has schemas for: `replyKeyboardMarkup`, `keyboardButtonRow`, `keyboardButton`, message entities (`messageEntityBold`, `messageEntityItalic`, `messageEntityCode`), media upload (`upload.saveFilePart`, `inputMediaUploadedPhoto`).

### Keyboard Format (REQUIRED)
- Use `single_use` NOT `one_time`
- `rows` must be `[{ _: 'keyboardButtonRow', buttons: [{ _: 'keyboardButton', text: '...' }] }]`

### Markdown Parsing
`parseMarkdown()` handles `*bold*`, `_italic_`, `` `code` `` — converts to message entities.

## WhatsApp Constraints
- Uses `whatsapp-web.js` — requires Chrome (Puppeteer)
- Auth stored in `/data/wwebjs_auth/` (LocalAuth)
- `LocalAuth` for session persistence
- Auto-reconnect on disconnect (unless logged out)
- Events: `qr`, `ready`, `disconnected`, `message`
- Media: `msg.downloadMedia()` returns base64 data; use `Buffer.from(data, 'base64')`

## Telegram Constraints
- `@mtproto/core` v6.3.0, layer 158
- `auth.importBotAuthorization` with BOT_TOKEN, API_ID, API_HASH
- Auth key persisted in `/data/tg_session.json`
- Flood wait handling: parse `FLOOD_WAIT_X`, wait X+5 seconds
- DC migration: parse `USER_MIGRATE_X`, retry on new DC
- Updates via `updates.getState` + `updates.getDifference` polling (every 15s)
- Update events: `updateNewMessage`, `updateShortMessage`, `updateShort`, `updates`, `updatesCombined`

## State Persistence
- `telegramChatId`, `telegramAccessHash`, `botEnabled` stored in `/data/state.json`
- `tgSend` uses `makePeer(chatId, telegramAccessHash)`
- `resolveUser(userId)` fetches `access_hash` via `users.getUsers`

## Web Interface
- `/` — QR display + Chat ID entry form
- `/ping` — health check (for uptime monitors)
- `/setchat` — POST form to set Chat ID manually
- CORS headers allow all origins

## Order Processing Flow (AI + Invoices)
- WhatsApp user sends order message → bot acknowledges immediately ("✅ تم استلام طلبك، سيتم معالجته قريباً")
- `queueOrder()` sets a 5-minute timer (300000ms) before AI processing
- After delay: `extractWithMistral()` calls Mistral AI (`mistral-large-latest`) to extract `{name, phone, product, quantity}` from the message
  - AI converts written numbers to digits (عشر الاف→10000, خمسة→5)
  - Uses `response_format: { type: 'json_object' }` for structured output
- `generateInvoiceImage()` in `invoice.js` launches Puppeteer → renders Arabic invoice HTML → screenshots to PNG
- Invoice image sent to Telegram admin via `tgSendPhoto()` (using `upload.saveFilePart` + `messages.sendMedia`)
- On failure, raw message forwarded to Telegram as fallback

## Invoice Module (`invoice.js`)
- Uses `puppeteer` (already installed) — launches separate browser instance per invoice
- Generates RTL Arabic HTML invoice with: #order, date, customer name, phone, product, quantity
- `generateInvoiceImage(info)` returns PNG Buffer

## AI Module (inline in `index.js`)
- Uses Mistral AI API (`https://api.mistral.ai/v1/chat/completions`)
- `MISTRAL_API_KEY` env var (fallback hardcoded)
- `fetch()` native in Node 22 — no extra SDK needed
- Prompt instructs Arabic number→digit conversion
