---
title: Wedding Invitation
emoji: 💍
colorFrom: pink
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
---

# 💍 Wedding Invitation Website

A bilingual (Khmer / English) wedding invitation website with a password-protected
admin panel for editing all text and uploading photos. Built with Flask, designed
for free hosting on Hugging Face Spaces.

## Features

- Elegant mobile-first invitation page with Khmer + English language toggle
- Live countdown to the wedding day
- Cover (hero) photo, photo gallery with lightbox
- Venue section with Google Maps link, RSVP link/phone
- `/admin` panel: edit every text field, upload/delete photos
- Data persistence via a private Hugging Face Dataset repo (survives Space restarts)

## Deploy on Hugging Face Spaces

1. **Create a Space** at https://huggingface.co/new-space
   - SDK: **Docker** (blank template)
   - Visibility: Public (so guests can open it)

2. **Create a private Dataset** at https://huggingface.co/new-dataset
   (e.g. `your-username/wedding-data`) — this stores your edits and photos.

3. **Create an access token** at https://huggingface.co/settings/tokens
   with **Write** permission.

4. In your Space → **Settings → Variables and secrets**, add secrets:

   | Name | Value |
   |------|-------|
   | `ADMIN_PASSWORD` | your admin password |
   | `SECRET_KEY` | any long random string |
   | `HF_TOKEN` | the write token from step 3 |
   | `DATASET_REPO` | `your-username/wedding-data` |

5. **Upload all project files** to the Space (web upload or `git push`).

6. Open your Space URL — the invitation is live. Go to `/admin` to edit.

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

Open http://localhost:7860 (admin: http://localhost:7860/admin, default password `admin123`).
