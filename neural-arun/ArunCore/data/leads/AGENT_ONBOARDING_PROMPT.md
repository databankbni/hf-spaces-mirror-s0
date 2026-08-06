# 🤖 COPY-PASTE PROMPT FOR ONBOARDING ANY NEW TUTOR / CLIENT

> **How to use this**:
> Simply copy the prompt template below, replace `[TUTOR_NAME]` and `[TUTOR_WEBSITE_OR_UDEMY_LINK]`, and paste it directly to your AI Coding Agent (AGY / Cursor / Claude)!

---

## 📋 COPY-PASTE PROMPT TEMPLATE FOR AI AGENT:

```markdown
Please read `demos/TUTOR_ONBOARDING_GUIDE.md` and copy `demos/general.json` to `data/leads/[tutor_id]_enterprise_dictionary.json`.

Use `data/leads/ed_donner_enterprise_dictionary.json` as your gold-standard reference example.

Your task is to onboard a new tutor named "[TUTOR_NAME]" (Website/Udemy Link: [TUTOR_WEBSITE_OR_UDEMY_LINK]).

Follow the step-by-step 6-phase protocol in `demos/TUTOR_ONBOARDING_GUIDE.md`:
1. Phase 1: Research their full name, role, title, avatar image URL, and bio.
2. Phase 2: Map official social links (Udemy, LinkedIn, X, YouTube, Website, GitHub) with emojis (🎓, 💼, 𝕏, ▶️, 🌐, 🐙) and contact info.
3. Phase 3: Research their real course catalog (titles, descriptions, pricing badges, target audience, key outcomes, enrollment links).
4. Phase 4: Create 4 suggested questions and 4 sidebar quick questions.
5. Phase 5: Extract their brand primary hex color and set `theme_design_system` CSS variables.
6. Phase 6: Configure backend LLM system prompt persona and language rules.

STRICT RULE: Do NOT make up false info if something is unlisted (e.g. private phone number or pricing); use clean professional fallbacks like "Custom / Inquire" or "Contact via Website".

Save the final JSON file at: `data/leads/[tutor_id]_enterprise_dictionary.json`
Save their headshot photo at: `frontend/public/[tutor_id].png`
Validate the JSON syntax when complete and confirm the URL: http://localhost:3000/?tutor=[tutor_id]
```

---

## 💡 EXAMPLE USAGE:

### Example: Onboarding Hitesh Choudhary (`hitesh`)
```markdown
Please read `demos/TUTOR_ONBOARDING_GUIDE.md` and copy `demos/general.json` to `data/leads/hitesh_enterprise_dictionary.json`.

Use `data/leads/ed_donner_enterprise_dictionary.json` as your gold-standard reference example.

Your task is to onboard a new tutor named "Hitesh Choudhary" (Website: https://hiteshchoudhary.com/ / YouTube: Chai aur Code).

Follow the step-by-step 6-phase protocol in `demos/TUTOR_ONBOARDING_GUIDE.md` and save the final JSON to `data/leads/hitesh_enterprise_dictionary.json` and photo to `frontend/public/hitesh.png`.
```
