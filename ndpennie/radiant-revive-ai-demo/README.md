---
title: Radiant Revive AI Demo
emoji: 🩺
colorFrom: red
colorTo: gray
sdk: gradio
sdk_version: 5.44.1
app_file: app.py
pinned: false
license: other
short_description: Fitzpatrick-aware dermatology AI demo
---

# Radiant Revive AI — Interactive Demo

**Fitzpatrick-aware dermatology AI · Nurse-in-the-loop · Clinical Decision Support**

Interactive demonstration scaffold for the Radiant Revive AI methodology.
Built for the Radiant Revive LLC UTA partnership meeting (July 2026).

## What this demo shows

- **Dual-axis skin-tone input** — Fitzpatrick Skin Type (FST 1-6) required; Monk Skin Tone (MST 1-10) optional, recorded as an independent axis per Measurement Protocol v1.1
- **Three-way clinical decision output** — safe to treat / refer to dermatology / urgent referral
- **Fitzpatrick-aware stratification** — model outputs commented on with skin-tone context
- **Confidence + malignancy probability** — displayed with per-Fitzpatrick calibration
- **Federal registration + IP posture** — company credentials in footer

## What this demo is NOT

⚠️ **Not for clinical use.** This is a Phase 1.2 sandbox scaffold with a placeholder predictor for user-interface demonstration only. The real Phase 1.3 trained Vision Transformer with Fitzpatrick-aware calibration head plugs in via the `predict_image()` function (currently mocked).

## About Radiant Revive LLC

- **Founder & PI:** Niya D. Pennie, BSN, RN — MSN/FNP Candidate at UT Arlington
- **Federal Registration:** SAM.gov ACTIVE · UEI EP6GX99FCN95 · CAGE 21GG3 · All Awards purpose
- **IP:** U.S. Utility Patent Application 19/643,795 (public) + U.S. Provisional (confidential)
- **Vendor Status:** Authorized PCA SKIN Professional Distributor
- **NAICS:** 812199 · 541512
- **Contact:** info@radiantrevivemedspa.com · (469) 213-8799 · radiantrevivemedspa.com

## Files

- `app.py` — Gradio interface (rename of radiant_revive_demo.py for HF Spaces)
- `requirements.txt` — dependencies
- `examples/` — three sample skin-patch tiles for one-click demo

---

© 2026 Radiant Revive LLC. Confidential. All rights reserved.
