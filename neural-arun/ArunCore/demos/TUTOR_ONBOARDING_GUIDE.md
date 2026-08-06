# 🤖 AI AGENT STEP-BY-STEP TUTOR ONBOARDING PROTOCOL

> **CRITICAL RULES FOR CODING AGENTS**:
> 1. **REFERENCE GOLD STANDARD**: Always inspect [`demos/ed_donner_enterprise_dictionary.json`](file:///home/arun/projects/profile/demos/ed_donner_enterprise_dictionary.json) or [`data/ed_donner_enterprise_dictionary.json`](file:///home/arun/projects/profile/data/ed_donner_enterprise_dictionary.json) as your **Gold Standard Reference Example** of how a completed, enterprise-grade tutor JSON file must look.
> 2. **NO HALLUCINATIONS / DO NOT MAKE UP INFO**: If you cannot find a specific piece of information (e.g. a direct phone number, specific course pricing, or private contact details) during your web research, **DO NOT MAKE IT UP OR INVENT FALSE FACTS**! Use a clean professional fallback (e.g., `"Custom / Inquire"`, `"Contact via Website"`, or use the standard fallback pattern from Ed's JSON example).
> 3. **STEP-BY-STEP ONLY**: **DO NOT** attempt to populate the entire JSON file at once! Populate the target `<tutor_id>_enterprise_dictionary.json` file **section-by-section, step-by-step** following the 6 sequential phases below.

---

## 📋 PREPARATION
1. Inspect [`demos/ed_donner_enterprise_dictionary.json`](file:///home/arun/projects/profile/demos/ed_donner_enterprise_dictionary.json) to understand the exact structure of a finished JSON dictionary.
2. Copy [`demos/general.json`](file:///home/arun/projects/profile/demos/general.json) to `data/<tutor_id>_enterprise_dictionary.json` and `demos/<tutor_id>_enterprise_dictionary.json`.
3. Save the tutor's official profile photo to `frontend/public/<tutor_id>.png`.

---

## 🔹 PHASE 1: BASIC IDENTITY & PROFILE
> **Goal**: Research and fill basic personal identity and profile metadata.

**Actions**:
- Perform targeted web search for tutor's full name, current role/title, company/achievements, and short bio.
- *Strict Rule*: If exact bio details are sparse, synthesize ONLY verified public facts — do NOT invent fictional companies or degrees.
- Fill the following fields in `data/<tutor_id>_enterprise_dictionary.json`:
  - `client_id`: `"<tutor_id>"` (lowercase snake_case, e.g., `"john_doe"`)
  - `name`: `"Full Name"`
  - `role`: `"Primary Tagline / Title"`
  - `title`: `"<First Name>'s AI Advisor"`
  - `subtitle`: `"Key Achievements & Highlights"`
  - `avatar`: `"/<tutor_id>.png"`
  - `cta_text`: `"Consult <First Name>"`
  - `welcome_message`: `"Hi! I'm <First Name>'s AI Advisor..."`
  - `about_text`: `"I'm <Full Name>... <Short Bio>"`
  - `client_metadata`: (`full_name`, `professional_title`, `niche`, `avatar_url`, `domain_url`)

---

## 🔹 PHASE 2: SOCIAL LINKS & CONTACT CHANNELS
> **Goal**: Map official social profiles and direct contact channels.

**Actions**:
- Search for the tutor's official verified links (Udemy, LinkedIn, X/Twitter, YouTube, Website, GitHub, WhatsApp).
- *Strict Rule*: If phone number or WhatsApp is not publicly listed, do NOT make up fake numbers! Use `"Contact via Email / Website"` or point to their domain contact page.
- Update the `socials` array:
  - Match each link with its appropriate `icon_key`: `"udemy"`, `"linkedin"`, `"x"`, `"youtube"`, `"website"`, `"github"`.
  - Assign matching `symbol_emoji`: `🎓` (Udemy), `💼` (LinkedIn), `𝕏` (Twitter/X), `▶️` (YouTube), `🌐` (Website), `🐙` (GitHub).
- Update `contact` object: `phone`, `whatsapp`, `email`, `website`.
- Sync `frontend_ui_dictionary.header.social_links` and `contact_modal.channels`.

---

## 🔹 PHASE 3: DEEP COURSE CATALOG RESEARCH
> **Goal**: Extract complete real-world course catalog and learning outcomes.

**Actions**:
- Perform web search: `site:udemy.com "<TUTOR_NAME>"` or check their personal website courses page.
- Extract for **each course**:
  - `id`: Unique slug (e.g. `"llm-masterclass"`)
  - `title`: Full official course title
  - `subtitle`: Subtitle or main value proposition
  - `description`: Detailed course summary
  - `price`: Pricing badge or track label (e.g. `"$199 / Bestseller"`, or `"Custom / Inquire"` if pricing is not public)
  - `target_audience`: Ideal audience
  - `outcomes`: Key skills or projects built
  - `link`: Direct enrollment URL
- *Strict Rule*: Rely strictly on verified course titles and curriculum outcomes from their Udemy/website listings. Do not make up fake course titles!
- Populate `courses` array in JSON.
- Sync `frontend_ui_dictionary.projects_view` (header title, subtitle, categories).

---

## 🔹 PHASE 4: TARGETED QUESTIONS & FAQS
> **Goal**: Generate high-intent question chips for quick user interaction.

**Actions**:
- Create **4 Suggested Questions** for the main chat hero card based on verified course topics:
  - 1 Beginner question
  - 1 Curriculum/Project question
  - 1 Access/Certificate question
  - 1 Consulting/Enterprise question
- Create **4 Sidebar Quick Questions**.
- Update `suggested_questions`, `sidebar_questions`, `chat_panel.suggested_questions_section.chips`, and `sidebar.quick_questions.prompts`.

---

## 🔹 PHASE 5: BRAND THEME & DESIGN SYSTEM
> **Goal**: Extract brand colors so the entire UI dynamically shifts to the tutor's personality.

**Actions**:
- Inspect the tutor's personal website / brand palette for their primary accent color.
- *Strict Rule*: Refer to Ed's example (`#0d9488` Teal) or Arun's example (`#10b981` Emerald) for proper RGBA and Hex formatting.
- Set `theme_design_system.brand_colors`:
  - `primary_green`: Primary accent Hex (e.g. `#0d9488` Teal, `#f97316` Orange, `#3b82f6` Blue)
  - `primary_hover`: Darker hover Hex
  - `accent_emerald`: Light accent Hex
- Set `theme_design_system.custom_css_variables`:
  - `--accent-green`: Primary accent Hex
  - `--accent-green-hover`: Darker hover Hex
  - `--border-accent`: `rgba(r, g, b, 0.35)`
  - `--bg-accent-soft`: `rgba(r, g, b, 0.08)`

---

## 🔹 PHASE 6: BACKEND LLM AGENT CONFIGURATION
> **Goal**: Program the AI LLM System Prompt so the backend chatbot answers accurately as the tutor's advisor.

**Actions**:
- Update `backend_llm_configuration.system_prompt`:
  - `persona_identity`: `"You are <Full Name>'s personal AI Advisor..."`
  - `voice_tone`: Tone guidelines matching tutor's public persona
  - `language_rules`: Exact language matching rules (English & Hinglish support)
  - `project_guidelines`: Key highlights to emphasize (courses, experience, verified background)
  - `hiring_consultation_flow`: Email share & Telegram alert rules

---

## 🔹 PHASE 7: VERIFICATION & AUDIT
> **Goal**: Ensure clean JSON syntax and zero runtime breakage.

**Run Verification Commands**:
```bash
# 1. Validate JSON syntax
python3 -m json.tool data/<tutor_id>_enterprise_dictionary.json > /dev/null && echo "✅ JSON Valid!"

# 2. Build Frontend to test TypeScript compilation
cd frontend && npm run build
```

**Live Test**:
- Open `http://localhost:3000/?tutor=<tutor_id>` in browser.
- Verify name, photo, brand colors, course catalog, social symbols, and live chat response against Ed Donner's reference standard!
