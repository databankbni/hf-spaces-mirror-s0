# 💰 PRODUCTION CLIENT ONBOARDING & DEPLOYMENT PLAYBOOK
> **Goal**: Step-by-step guide to onboarding, configuring, deploying, and collecting recurring revenue when a client pays **$300 – $1,500** for a custom AI Advisor on your platform.

---

## 📑 TABLE OF CONTENTS
1. [Offer Breakdown & What the Client Gets](#1-offer-breakdown--what-the-client-gets)
2. [Client Information Intake Checklist](#2-client-information-intake-checklist)
3. [Step-by-Step Technical Onboarding (15–30 Mins)](#3-step-by-step-technical-onboarding-1530-mins)
4. [Production Deployment Architecture](#4-production-deployment-architecture)
5. [Configuring Custom Subdomain (e.g. advisor.client.com)](#5-configuring-custom-subdomain)
6. [Client Delivery Email & Handoff Template](#6-client-delivery-email--handoff-template)
7. [Upselling & Monthly Retainer ($99–$299/mo)](#7-upselling--monthly-retainer)

---

## 1. OFFER BREAKDOWN & WHAT THE CLIENT GETS

When a client pays you **$300 (or setup fee)**, you provide:

1. **Custom 24/7 AI Course & Sales Advisor**:
   - An interactive AI Assistant trained on their bio, experience, course catalog, pricing, and FAQ.
2. **Brand Theme Integration**:
   - Matching their brand's primary colors, fonts, avatar, and social links (`🎓`, `💼`, `𝕏`, `🌐`, `▶️`, `🐙`).
3. **Instant Telegram 3-Way Live Takeover Alerts**:
   - When a student or enterprise client chats, an alert is sent to the client's Telegram with a **1-Click Join Link**.
   - The client can tap the link on their phone and talk to the student live inside the chat room alongside the AI.
4. **Hosted URL & Custom Domain**:
   - Hosted on `yourdomain.com/?tutor=<client_id>` or `advisor.<clientdomain>.com`.

---

## 2. CLIENT INFORMATION INTAKE CHECKLIST

Send this quick 5-minute intake checklist to the client after receiving payment:

```markdown
📋 CLIENT INTAKE FORM:
1. Full Name & Primary Professional Title (e.g. "Dr. Alex Xu, Author & System Design Educator")
2. Personal / Company Website URL
3. Profile Photo / Headshot (High-res PNG or JPG)
4. Brand Primary Hex Color (e.g. #0d9488 Teal, #f97316 Orange, #2563eb Blue)
5. Course Catalog / Service List (Titles, Descriptions, Prices, Udemy/Website links)
6. Official Social Links (Udemy, LinkedIn, X/Twitter, YouTube, GitHub)
7. Direct Email & Phone / WhatsApp number for student inquiries
8. Telegram Chat ID (for receiving instant lead alerts on phone)
```

---

## 3. STEP-BY-STEP TECHNICAL ONBOARDING (15–30 MINS)

Follow this exact sequence to build their custom portal without writing new code:

### Step 3.1: Create Client JSON
1. Duplicate [`demos/general.json`](file:///home/arun/projects/profile/demos/general.json) $\rightarrow$ `data/<client_id>_enterprise_dictionary.json`.
2. Duplicate [`demos/general.json`](file:///home/arun/projects/profile/demos/general.json) $\rightarrow$ `demos/<client_id>_enterprise_dictionary.json`.

### Step 3.2: Save Avatar Asset
Save their headshot to `frontend/public/<client_id>.png` (or `.jpg`).

### Step 3.3: Execute Onboarding Protocol
Follow [`demos/TUTOR_ONBOARDING_GUIDE.md`](file:///home/arun/projects/profile/demos/TUTOR_ONBOARDING_GUIDE.md) phase by phase:
- **Phase 1**: Fill `name`, `role`, `subtitle`, `welcome_message`, `about_text`.
- **Phase 2**: Map social links (`udemy`, `linkedin`, `x`, `website`) and contact channels.
- **Phase 3**: Fill course catalog (`courses` array) with titles, descriptions, price badges, and outcomes.
- **Phase 4**: Set 4 suggested questions and 4 sidebar quick questions.
- **Phase 5**: Set `brand_colors` (primary hex, hover hex) and CSS variables (`--accent-green`, `--border-accent`).
- **Phase 6**: Set system prompt persona and voice & tone.

### Step 3.4: Local Verification
```bash
# Validate JSON syntax
python3 -m json.tool data/<client_id>_enterprise_dictionary.json > /dev/null && echo "✅ JSON Valid!"

# Verify local UI render
# Open http://localhost:3000/?tutor=<client_id>
```

---

## 4. PRODUCTION DEPLOYMENT ARCHITECTURE

To deploy for production with 99.9% uptime and $0–$5/month server cost:

### Component 1: Frontend (Vercel)
1. Push repo to GitHub (`git push origin main`).
2. Connect repo to [Vercel](https://vercel.com).
3. Set Vercel Build Settings:
   - Root Directory: `frontend`
   - Framework Preset: `Next.js`

### Component 2: Backend API (Railway / Render / Hugging Face / VPS)
1. Deploy `core/api.py` FastAPI app to **Railway.app** or **Render.com**.
2. Environment Variables to set in Railway/Render:
   ```env
   OPENAI_API_KEY=sk-proj-...
   TELEGRAM_BOT_TOKEN=8847600936:...
   TELEGRAM_CHAT_ID=<CLIENT_TELEGRAM_CHAT_ID>
   ```

---

## 5. CONFIGURING CUSTOM SUBDOMAIN (e.g. advisor.client.com)

If the client wants the AI Advisor hosted on their own domain:

1. In **Vercel Project Settings** $\rightarrow$ **Domains** $\rightarrow$ Add `advisor.clientdomain.com`.
2. Tell the client to add a **CNAME DNS record** in their domain registrar (Cloudflare / Namecheap / GoDaddy):
   - **Type**: `CNAME`
   - **Name / Host**: `advisor`
   - **Target / Value**: `cname.vercel-dns.com`
3. Vercel automatically issues a free SSL certificate within 2 minutes!

---

## 6. CLIENT DELIVERY EMAIL & HANDOFF TEMPLATE

Copy-paste this exact delivery email when handing off the product:

```markdown
Subject: 🚀 Your 24/7 AI Course Advisor & Sales Portal is LIVE!

Hi [Client Name],

Great news! Your custom 24/7 AI Course Advisor & Sales Portal is officially live and ready for your students!

🌐 Your Live Portal Link:
https://[advisor.yourdomain.com] (or https://yourdomain.com/?tutor=[client_id])

✨ Features Included in Your Deployment:
1. 24/7 Student Q&A: Trained on your bio, background, and full course catalog.
2. Direct Course Recommendations: Guides prospective students directly to your enrollment links.
3. Brand Theme Integration: Customized with your official brand colors and headshot.
4. Live 1-Click Telegram Alerts: Whenever a high-intent student or enterprise client reaches out, an instant alert is sent to your phone. Tap the 1-click link in Telegram to join the conversation live!

Let me know if you would like any minor tweaks to your course listings or bio!

Best regards,
Arun Yadav
AI Systems Architect
```

---

## 7. UPSELLING & MONTHLY RETAINER ($99–$299/MO)

After delivering the $300 setup, offer them an ongoing maintenance retainer:

> *"For **$99/month**, I provide ongoing hosting, OpenAI API key usage management, monthly course catalog updates, and priority Telegram handoff bot maintenance."*

With **10 clients** on retainer:
- **Upfront Setup Revenue**: $3,000 – $5,000
- **Monthly Recurring Revenue (MRR)**: $1,000 – $2,990 / month
- **Time Required to Maintain**: Less than 2 hours per month! 🚀
