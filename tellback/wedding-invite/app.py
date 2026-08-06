import csv
import hashlib
import io
import json
import os
import re
import secrets
import threading
import time
import urllib.parse
import urllib.request
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import (Flask, Response, flash, redirect, render_template, request,
                   send_from_directory, session, url_for)
from PIL import Image, ImageDraw, ImageFont, ImageOps
from werkzeug.middleware.proxy_fix import ProxyFix

import storage

app = Flask(__name__)
# HF Spaces sits behind a reverse proxy; trust its headers so url_for(_external=True)
# generates https:// links (needed for the og:image social preview).
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config["MAX_CONTENT_LENGTH"] = 80 * 1024 * 1024  # 80 MB (video uploads)
# Static assets are cached long; ?v= (ASSET_V) busts the cache on each deploy.
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 30 * 24 * 3600
ASSET_V = str(int(time.time()))

try:
    from flask_compress import Compress
    Compress(app)  # gzip/brotli for HTML/CSS/JS responses
except ImportError:
    print("[app] flask-compress not installed; responses served uncompressed")


@app.context_processor
def inject_asset_version():
    return {"asset_v": ASSET_V}

# Serializes read-modify-write cycles on the JSON files so concurrent
# submissions can't overwrite each other (server must run single-process).
DATA_LOCK = threading.Lock()

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}
AUDIO_EXTENSIONS = {"mp3", "m4a", "ogg", "wav"}
VIDEO_EXTENSIONS = {"mp4", "webm", "mov", "m4v"}

# Choices offered in the admin "Design & Features" panel
THEME_PRESETS = [
    ("Gold", "#c9a84c"), ("Rose Gold", "#c48b9f"), ("Burgundy", "#8e3b46"),
    ("Emerald", "#2e7d5b"), ("Navy", "#34558b"),
]
KH_HEADING_FONTS = ["Moul", "Koulen", "Dangrek", "Battambang", "Bokor"]
SCRIPT_FONTS = ["Great Vibes", "Dancing Script", "Allura", "Parisienne"]
SECTION_LABELS = [
    ("invitation", "💌 Invitation"), ("story", "💞 Love Story"),
    ("countdown", "⏳ Countdown"),
    ("schedule", "🕐 Schedule"), ("venue", "📍 Venue"),
    ("dress", "👗 Dress Code"),
    ("apology", "🙏 Thank You & Apology"), ("gallery", "📸 Gallery"),
    ("guest_photos", "📷 Guest Photos"), ("video", "🎬 Video"),
    ("wishes", "💬 Wishes"), ("faq", "❓ FAQ"),
    ("rsvp", "✅ RSVP"), ("gift", "🎁 KHQR Gift"),
]
SECTION_IDS = [s for s, _ in SECTION_LABELS]

# Editable text fields shown in the admin panel, grouped into collapsible
# sections: (group title, [(key, label, widget), ...])
FIELD_GROUPS = [
    ("💑 Couple & Families", [
        ("groom_name_kh", "Groom's Name (Khmer)", "input"),
        ("groom_name_en", "Groom's Name (English)", "input"),
        ("bride_name_kh", "Bride's Name (Khmer)", "input"),
        ("bride_name_en", "Bride's Name (English)", "input"),
        ("groom_father_kh", "Groom's Father (Khmer)", "input"),
        ("groom_father_en", "Groom's Father (English)", "input"),
        ("groom_mother_kh", "Groom's Mother (Khmer)", "input"),
        ("groom_mother_en", "Groom's Mother (English)", "input"),
        ("bride_father_kh", "Bride's Father (Khmer)", "input"),
        ("bride_father_en", "Bride's Father (English)", "input"),
        ("bride_mother_kh", "Bride's Mother (Khmer)", "input"),
        ("bride_mother_en", "Bride's Mother (English)", "input"),
        ("label_groom_family_kh", "\"Groom's Family\" Label (Khmer)", "input"),
        ("label_groom_family_en", "\"Groom's Family\" Label (English)", "input"),
        ("label_bride_family_kh", "\"Bride's Family\" Label (Khmer)", "input"),
        ("label_bride_family_en", "\"Bride's Family\" Label (English)", "input"),
    ]),
    ("💌 Invitation Text", [
        ("eyebrow_kh", "Top Line above Names (Khmer)", "input"),
        ("eyebrow_en", "Top Line above Names (English)", "input"),
        ("greeting_kh", "Guest Greeting Word (Khmer)", "input"),
        ("greeting_en", "Guest Greeting Word (English)", "input"),
        ("invite_kh", "Invitation Message (Khmer)", "textarea"),
        ("invite_en", "Invitation Message (English)", "textarea"),
        ("btn_open_kh", "\"Tap to Open\" Envelope Button (Khmer)", "input"),
        ("btn_open_en", "\"Tap to Open\" Envelope Button (English)", "input"),
    ]),
    ("📅 Date & Countdown", [
        ("date_iso", "Wedding Date/Time ISO — for countdown (e.g. 2026-12-26T07:00:00+07:00)", "input"),
        ("date_kh", "Wedding Date (Khmer)", "input"),
        ("date_en", "Wedding Date (English)", "input"),
        ("time_display_kh", "Ceremony Time (Khmer, e.g. ម៉ោង ៧:០០ ព្រឹក)", "input"),
        ("time_display_en", "Ceremony Time (English, e.g. 7:00 AM)", "input"),
        ("label_days_kh", "\"Days\" (Khmer)", "input"),
        ("label_days_en", "\"Days\" (English)", "input"),
        ("label_hours_kh", "\"Hours\" (Khmer)", "input"),
        ("label_hours_en", "\"Hours\" (English)", "input"),
        ("label_minutes_kh", "\"Minutes\" (Khmer)", "input"),
        ("label_minutes_en", "\"Minutes\" (English)", "input"),
        ("label_seconds_kh", "\"Seconds\" (Khmer)", "input"),
        ("label_seconds_en", "\"Seconds\" (English)", "input"),
    ]),
    ("📍 Venue", [
        ("venue_name_kh", "Venue Name (Khmer)", "input"),
        ("venue_name_en", "Venue Name (English)", "input"),
        ("venue_address_kh", "Venue Address (Khmer)", "textarea"),
        ("venue_address_en", "Venue Address (English)", "textarea"),
        ("maps_url", "Google Maps Link", "input"),
        ("btn_maps_kh", "Maps Button Text (Khmer)", "input"),
        ("btn_maps_en", "Maps Button Text (English)", "input"),
        ("ride_url", "Ride Link (Grab/PassApp share link, optional)", "input"),
        ("btn_ride_kh", "Ride Button Text (Khmer)", "input"),
        ("btn_ride_en", "Ride Button Text (English)", "input"),
        ("btn_calendar_kh", "Add-to-Calendar Button (Khmer)", "input"),
        ("btn_calendar_en", "Add-to-Calendar Button (English)", "input"),
    ]),
    ("🏷 Section Titles", [
        ("title_invitation_kh", "Invitation Section (Khmer)", "input"),
        ("title_invitation_en", "Invitation Section (English)", "input"),
        ("title_countdown_kh", "Countdown Section (Khmer)", "input"),
        ("title_countdown_en", "Countdown Section (English)", "input"),
        ("title_schedule_kh", "Schedule Section (Khmer)", "input"),
        ("title_schedule_en", "Schedule Section (English)", "input"),
        ("title_venue_kh", "Venue Section (Khmer)", "input"),
        ("title_venue_en", "Venue Section (English)", "input"),
        ("title_gallery_kh", "Gallery Section (Khmer)", "input"),
        ("title_gallery_en", "Gallery Section (English)", "input"),
        ("title_gift_kh", "Gift/KHQR Section (Khmer)", "input"),
        ("title_gift_en", "Gift/KHQR Section (English)", "input"),
        ("title_wishes_kh", "Wishes Section (Khmer)", "input"),
        ("title_wishes_en", "Wishes Section (English)", "input"),
        ("title_rsvp_kh", "RSVP Section (Khmer)", "input"),
        ("title_rsvp_en", "RSVP Section (English)", "input"),
    ]),
    ("🎁 Gift / KHQR Text", [
        ("gift_note_kh", "Gift Note (Khmer)", "textarea"),
        ("gift_note_en", "Gift Note (English)", "textarea"),
        ("qr_hint_kh", "Tap-QR-to-Share Hint (Khmer)", "input"),
        ("qr_hint_en", "Tap-QR-to-Share Hint (English)", "input"),
        ("khqr_side_groom_kh", "\"Groom's Side\" Label (Khmer)", "input"),
        ("khqr_side_groom_en", "\"Groom's Side\" Label (English)", "input"),
        ("khqr_side_bride_kh", "\"Bride's Side\" Label (Khmer)", "input"),
        ("khqr_side_bride_en", "\"Bride's Side\" Label (English)", "input"),
    ]),
    ("📝 Form Labels & Buttons", [
        ("label_name_kh", "\"Your name\" (Khmer)", "input"),
        ("label_name_en", "\"Your name\" (English)", "input"),
        ("label_message_kh", "\"Your message\" (Khmer)", "input"),
        ("label_message_en", "\"Your message\" (English)", "input"),
        ("btn_wish_kh", "Send Wishes Button (Khmer)", "input"),
        ("btn_wish_en", "Send Wishes Button (English)", "input"),
        ("label_attend_yes_kh", "\"Attending\" Option (Khmer)", "input"),
        ("label_attend_yes_en", "\"Attending\" Option (English)", "input"),
        ("label_attend_no_kh", "\"Can't attend\" Option (Khmer)", "input"),
        ("label_attend_no_en", "\"Can't attend\" Option (English)", "input"),
        ("label_guests_kh", "\"Number of guests\" (Khmer)", "input"),
        ("label_guests_en", "\"Number of guests\" (English)", "input"),
        ("label_note_kh", "\"Note (optional)\" (Khmer)", "input"),
        ("label_note_en", "\"Note (optional)\" (English)", "input"),
        ("label_companions_kh", "\"Companion names\" (Khmer)", "input"),
        ("label_companions_en", "\"Companion names\" (English)", "input"),
        ("btn_rsvp_kh", "Confirm RSVP Button (Khmer)", "input"),
        ("btn_rsvp_en", "Confirm RSVP Button (English)", "input"),
        ("toast_rsvp_kh", "RSVP Thank-You Popup (Khmer)", "input"),
        ("toast_rsvp_en", "RSVP Thank-You Popup (English)", "input"),
        ("toast_wish_kh", "Wishes Thank-You Popup (Khmer)", "input"),
        ("toast_wish_en", "Wishes Thank-You Popup (English)", "input"),
        ("rsvp_phone", "RSVP Phone / Telegram", "input"),
    ]),
    ("🙏 Thank You & Apology Section", [
        ("apology_title_kh", "Section Title (Khmer)", "input"),
        ("apology_title_en", "Section Title (English)", "input"),
        ("apology_kh", "Message (Khmer)", "textarea"),
        ("apology_en", "Message (English)", "textarea"),
    ]),
    ("🎉 After the Wedding & Footer", [
        ("thank_you_kh", "Thank-You Message shown after the wedding (Khmer)", "textarea"),
        ("thank_you_en", "Thank-You Message shown after the wedding (English)", "textarea"),
        ("married_days_kh", "\"Married for X days\" line — {d} becomes the number (Khmer)", "input"),
        ("married_days_en", "\"Married for X days\" line — {d} becomes the number (English)", "input"),
        ("footer_kh", "Footer Message (Khmer)", "input"),
        ("footer_en", "Footer Message (English)", "input"),
    ]),
    ("🎬 Video & 👗 Dress Code", [
        ("title_video_kh", "Video Section Title (Khmer)", "input"),
        ("title_video_en", "Video Section Title (English)", "input"),
        ("video_url", "YouTube Video Link (or upload a file in the 🎬 Video card)", "input"),
        ("live_url", "Live Stream Link — shows a Watch Live button (optional)", "input"),
        ("btn_live_kh", "Watch Live Button (Khmer)", "input"),
        ("btn_live_en", "Watch Live Button (English)", "input"),
        ("title_story_kh", "Love Story Section Title (Khmer)", "input"),
        ("title_story_en", "Love Story Section Title (English)", "input"),
        ("title_faq_kh", "FAQ Section Title (Khmer)", "input"),
        ("title_faq_en", "FAQ Section Title (English)", "input"),
        ("dress_title_kh", "Dress Code Title (Khmer)", "input"),
        ("dress_title_en", "Dress Code Title (English)", "input"),
        ("dress_note_kh", "Dress Code Note (Khmer)", "input"),
        ("dress_note_en", "Dress Code Note (English)", "input"),
        ("dress_colors", "Dress Code Colors (hex codes, comma-separated)", "input"),
    ]),
    ("📷 Guest Photos, Tables & RSVP Closing", [
        ("guest_photos_title_kh", "Guest Photos Section Title (Khmer)", "input"),
        ("guest_photos_title_en", "Guest Photos Section Title (English)", "input"),
        ("upload_note_kh", "Guest Upload Note (Khmer)", "input"),
        ("upload_note_en", "Guest Upload Note (English)", "input"),
        ("btn_upload_kh", "Send Photos Button (Khmer)", "input"),
        ("btn_upload_en", "Send Photos Button (English)", "input"),
        ("toast_upload_kh", "Upload Thank-You Popup (Khmer)", "input"),
        ("toast_upload_en", "Upload Thank-You Popup (English)", "input"),
        ("table_label_kh", "\"Table\" Label (Khmer)", "input"),
        ("table_label_en", "\"Table\" Label (English)", "input"),
        ("voice_hint_kh", "Voice Blessing Hint (Khmer)", "input"),
        ("voice_hint_en", "Voice Blessing Hint (English)", "input"),
        ("toast_voice_kh", "Voice Thank-You Popup (Khmer)", "input"),
        ("toast_voice_en", "Voice Thank-You Popup (English)", "input"),
        ("btn_selfie_kh", "Selfie Frame Button (Khmer)", "input"),
        ("btn_selfie_en", "Selfie Frame Button (English)", "input"),
        ("rsvp_closed_kh", "RSVP-Closed Message (Khmer)", "textarea"),
        ("rsvp_closed_en", "RSVP-Closed Message (English)", "textarea"),
    ]),
]

FIELDS = [field for _, group_fields in FIELD_GROUPS for field in group_fields]

DEFAULT_CONTENT = {
    "groom_name_kh": "តាន់ ម៉េងហុង",
    "groom_name_en": "Tann Menghong",
    "bride_name_kh": "អ៊ុក សុខខា",
    "bride_name_en": "Ouk Sokha",
    "groom_father_kh": "លោក តាន់ ម៉ៅ",
    "groom_father_en": "Mr. Tann Mao",
    "groom_mother_kh": "អ្នកស្រី ឈុំ ឡាវិន",
    "groom_mother_en": "Mrs. Chhum Lavin",
    "bride_father_kh": "លោក អ៊ុក ធឿន",
    "bride_father_en": "Mr. Ouk Thoeun",
    "bride_mother_kh": "អ្នកស្រី ទឹម លីន",
    "bride_mother_en": "Mrs. Tim Lin",
    "invite_kh": "យើងខ្ញុំមានកិត្តិយសសូមគោរពអញ្ជើញ លោក លោកស្រី អ្នកនាងកញ្ញា អញ្ជើញចូលរួមក្នុងពិធីមង្គលអាពាហ៍ពិពាហ៍ របស់យើងខ្ញុំ ដើម្បីជាកិត្តិយស និងប្រសិទ្ធពរជ័យ។",
    "invite_en": "Together with our families, we joyfully invite you to celebrate our wedding day. Your presence is the greatest gift we could ask for.",
    "date_iso": "2026-12-26T07:00:00+07:00",
    "date_kh": "ថ្ងៃសៅរ៍ ទី២៦ ខែធ្នូ ឆ្នាំ២០២៦",
    "date_en": "Saturday, 26 December 2026",
    "time_display_kh": "ម៉ោង ៧:០០ ព្រឹក",
    "time_display_en": "7:00 AM",
    "venue_name_kh": "សណ្ឋាគារ ភ្នំពេញ",
    "venue_name_en": "Phnom Penh Hotel",
    "venue_address_kh": "មហាវិថីព្រះមុនីវង្ស រាជធានីភ្នំពេញ",
    "venue_address_en": "Monivong Blvd, Phnom Penh, Cambodia",
    "maps_url": "https://maps.google.com",
    "rsvp_phone": "+855 12 345 678",
    "thank_you_kh": "សូមអរគុណយ៉ាងជ្រាលជ្រៅ ចំពោះការចូលរួម និងពរជ័យរបស់លោកអ្នក។ យើងបានរៀបការហើយ! 🎉",
    "thank_you_en": "Thank you from the bottom of our hearts for your presence and blessings. We are married! 🎉",
    "footer_kh": "សូមអរគុណសម្រាប់ការចូលរួម ❤",
    "footer_en": "We look forward to celebrating with you ❤",
    "eyebrow_kh": "សិរីមង្គលអាពាហ៍ពិពាហ៍",
    "eyebrow_en": "Wedding Invitation",
    "greeting_kh": "ជូនចំពោះ",
    "greeting_en": "Dear",
    "label_groom_family_kh": "គ្រួសារកូនប្រុស",
    "label_groom_family_en": "Groom's Family",
    "label_bride_family_kh": "គ្រួសារកូនស្រី",
    "label_bride_family_en": "Bride's Family",
    "label_days_kh": "ថ្ងៃ",
    "label_days_en": "Days",
    "label_hours_kh": "ម៉ោង",
    "label_hours_en": "Hours",
    "label_minutes_kh": "នាទី",
    "label_minutes_en": "Minutes",
    "label_seconds_kh": "វិនាទី",
    "label_seconds_en": "Seconds",
    "title_invitation_kh": "សេចក្តីអញ្ជើញ",
    "title_invitation_en": "Our Invitation",
    "title_countdown_kh": "រាប់ថយក្រោយ",
    "title_countdown_en": "Counting Down",
    "title_schedule_kh": "កម្មវិធីពិធីមង្គលការ",
    "title_schedule_en": "Wedding Schedule",
    "title_venue_kh": "ទីកន្លែងប្រារព្ធពិធី",
    "title_venue_en": "Venue",
    "title_gallery_kh": "វិចិត្រសាលរូបភាព",
    "title_gallery_en": "Our Gallery",
    "title_gift_kh": "ចងដៃតាម KHQR",
    "title_gift_en": "Wedding Gift (KHQR)",
    "title_wishes_kh": "សារជូនពរ",
    "title_wishes_en": "Wishes for the Couple",
    "title_rsvp_kh": "បញ្ជាក់ការចូលរួម",
    "title_rsvp_en": "RSVP",
    "gift_note_kh": "សម្រាប់លោកអ្នកដែលមិនអាចចូលរួមបាន អាចចងដៃតាមរយៈ KHQR ខាងក្រោម",
    "gift_note_en": "If you would like to send a gift, you can scan the KHQR code below.",
    "btn_maps_kh": "បើកផែនទី Google Maps",
    "btn_maps_en": "Open in Google Maps",
    "btn_calendar_kh": "រក្សាទុកក្នុងប្រតិទិន 📅",
    "btn_calendar_en": "Add to Calendar 📅",
    "btn_open_kh": "ចុចដើម្បីបើកធៀប",
    "btn_open_en": "Tap to Open",
    "qr_hint_kh": "ចុចលើ QR ដើម្បីរក្សាទុក ឬចែករំលែក",
    "qr_hint_en": "Tap the QR code to save or share it",
    "label_name_kh": "ឈ្មោះរបស់អ្នក",
    "label_name_en": "Your name",
    "label_message_kh": "សារជូនពរ",
    "label_message_en": "Your message",
    "btn_wish_kh": "ផ្ញើពរជ័យ ❤",
    "btn_wish_en": "Send Wishes ❤",
    "label_attend_yes_kh": "ចូលរួម 🎉",
    "label_attend_yes_en": "Attending 🎉",
    "label_attend_no_kh": "មិនអាចចូលរួម",
    "label_attend_no_en": "Can't attend",
    "label_guests_kh": "ចំនួនភ្ញៀវ",
    "label_guests_en": "Number of guests",
    "label_note_kh": "សារបន្ថែម (មិនចាំបាច់)",
    "label_note_en": "Note (optional)",
    "label_companions_kh": "ឈ្មោះអ្នករួមដំណើរ (មិនចាំបាច់)",
    "label_companions_en": "Companion names (optional)",
    "btn_rsvp_kh": "បញ្ជាក់ការចូលរួម",
    "btn_rsvp_en": "Confirm RSVP",
    "toast_rsvp_kh": "សូមអរគុណ! ការបញ្ជាក់របស់អ្នកត្រូវបានទទួល ❤",
    "toast_rsvp_en": "Thank you! Your RSVP has been received ❤",
    "toast_wish_kh": "សូមអរគុណសម្រាប់ពរជ័យ! ❤",
    "toast_wish_en": "Thank you for your wishes! ❤",
    "apology_title_kh": "សូមអរគុណ និងសូមអភ័យទោស",
    "apology_title_en": "Thank You & Our Apologies",
    "apology_kh": "យើងខ្ញុំទាំងពីរ សូមថ្លែងអំណរគុណ យ៉ាងជ្រាលជ្រៅ ចំពោះវត្តមាន ដ៏ឧត្តុង្គឧត្តមរបស់ សម្តេច ឯកឧត្តម លោកជំទាវ លោកអ្នកឧកញ៉ា អ្នកឧកញ៉ា ឧកញ៉ា លោក លោកស្រី អ្នកនាង កញ្ញា ដែលបានអញ្ជើញចូលរួម ជាកិត្តិយស ក្នុងពិធីសិរីសួស្តីអាពាហ៍ពិពាហ៍ របស់យើងខ្ញុំ នាពេលខាងមុខនេះ។ យើងខ្ញុំសូមការខន្តីអភ័យទោស ដែលពុំបានជូនលិខិតអញ្ជើញដោយផ្ទាល់។ ដោយការគោរពដ៏ខ្ពង់ខ្ពស់ពីយើងខ្ញុំ។\n\nវត្តមានរបស់អស់លោកអ្នកគឺជាអំណោយដ៏មានតម្លៃបំផុតសម្រាប់យើងរួចទៅហើយ។",
    "apology_en": "From the bottom of our hearts, we sincerely thank all our honored guests for gracing our wedding ceremony with your presence. We humbly apologize for not being able to deliver the invitation in person. With our deepest respect.\n\nYour presence is already the most precious gift for us.",
    "schedule": [
        {"time": "07:00 AM", "title_kh": "ពិធីហែជំនូន", "title_en": "Groom's Procession"},
        {"time": "08:30 AM", "title_kh": "ពិធីកាត់សក់", "title_en": "Hair Cutting Ceremony"},
        {"time": "10:00 AM", "title_kh": "ពិធីសំពះផ្ទឹម", "title_en": "Knot Tying Ceremony"},
        {"time": "05:00 PM", "title_kh": "ពិធីជប់លៀង", "title_en": "Dinner Reception"},
    ],
    "hero_photo": "",
    "bg_photo": "",
    "gallery": [],
    "khqr_groom_usd": "",
    "khqr_groom_khr": "",
    "khqr_bride_usd": "",
    "khqr_bride_khr": "",
    "khqr_side_groom_kh": "ខាងកូនប្រុស",
    "khqr_side_groom_en": "Groom's Side",
    "khqr_side_bride_kh": "ខាងកូនស្រី",
    "khqr_side_bride_en": "Bride's Side",
    "music": "",
    # Design & feature settings (admin "Design & Features" panel)
    "theme_color": "#c9a84c",
    "bg_overlay": "0.25",
    "font_kh_heading": "Moul",
    "font_en_script": "Great Vibes",
    "petal_emoji": "🌸",
    "petal_count": "5",
    "show_envelope": "yes",
    "hero_slideshow": "no",
    "guest_upload": "no",
    "rsvp_deadline": "",
    "section_order": list(SECTION_IDS),
    "section_hidden": [],
    # Master guest list: [{"name": ..., "table": ...}, ...] — feeds the
    # personalized links, table badges, tracking and QR codes
    "guest_list": [],
    "invite_template": "សូមគោរពអញ្ជើញ {name} ចូលរួមជាភ្ញៀវកិត្តិយស "
                       "ក្នុងពិធីមង្គលអាពាហ៍ពិពាហ៍របស់យើងខ្ញុំ 💍\n{link}",
    "remind_template": "សូមរំលឹកដោយក្តីគោរព {name} 🙏 យើងខ្ញុំរង់ចាំ"
                       "ការបញ្ជាក់ការចូលរួមរបស់អ្នក\n{link}",
    "video_url": "",
    "video": "",
    "title_video_kh": "វីដេអូ Pre-Wedding",
    "title_video_en": "Pre-Wedding Video",
    "dress_title_kh": "កូដសម្លៀកបំពាក់",
    "dress_title_en": "Dress Code",
    "dress_note_kh": "សូមស្លៀកពាក់តាមពណ៌ទាំងនេះ ដើម្បីរួមគ្នាបង្កើតអនុស្សាវរីយ៍ដ៏ស្រស់ស្អាត",
    "dress_note_en": "We would love to see you in these colors",
    "dress_colors": "#c9a84c, #f7e8ea, #8e3b46",
    "married_days_kh": "រៀបការបាន {d} ថ្ងៃហើយ ❤",
    "married_days_en": "Married for {d} days ❤",
    "default_lang": "kh",
    "after_mode": "no",
    "voice_wishes": "no",
    "thanks_template": "សូមអរគុណ {name} យ៉ាងជ្រាលជ្រៅ ដែលបានចូលរួមអបអរសាទរ "
                       "ក្នុងពិធីមង្គលការរបស់យើងខ្ញុំ ❤\n{link}",
    "title_story_kh": "រឿងរ៉ាវស្នេហ៍របស់យើង",
    "title_story_en": "Our Love Story",
    "story": [],
    "title_faq_kh": "សំណួរ​ដែលសួរញឹកញាប់",
    "title_faq_en": "Questions & Answers",
    "faq": [],
    "live_url": "",
    "btn_live_kh": "🔴 មើលការផ្សាយផ្ទាល់",
    "btn_live_en": "🔴 Watch Live",
    "ride_url": "",
    "btn_ride_kh": "កក់ឡានទៅកន្លែងពិធី 🚕",
    "btn_ride_en": "Book a ride 🚕",
    "voice_hint_kh": "ថតសំឡេងជូនពរ (បង្ហាញបន្ទាប់ពីការពិនិត្យ)",
    "voice_hint_en": "Record a voice blessing (shown after review)",
    "toast_voice_kh": "សូមអរគុណ! សំឡេងជូនពរនឹងបង្ហាញបន្ទាប់ពីការពិនិត្យ ❤",
    "toast_voice_en": "Thank you! Your voice blessing will appear after review ❤",
    "btn_selfie_kh": "📸 សែលហ្វីជាមួយស៊ុមមង្គលការ",
    "btn_selfie_en": "📸 Selfie with our wedding frame",
    "guest_photos_title_kh": "រូបភាពពីភ្ញៀវ",
    "guest_photos_title_en": "Photos from Guests",
    "upload_note_kh": "ចែករំលែករូបភាពរបស់អ្នកជាមួយយើង",
    "upload_note_en": "Share your photos of our day with us",
    "btn_upload_kh": "ផ្ញើរូបភាព 📷",
    "btn_upload_en": "Send Photos 📷",
    "toast_upload_kh": "សូមអរគុណ! រូបភាពនឹងបង្ហាញបន្ទាប់ពីការពិនិត្យ ❤",
    "toast_upload_en": "Thank you! Your photos will appear after review ❤",
    "table_label_kh": "តុលេខ",
    "table_label_en": "Table",
    "rsvp_closed_kh": "ការបញ្ជាក់ការចូលរួមត្រូវបានបិទហើយ។ សូមទាក់ទងតាមទូរស័ព្ទខាងក្រោម។",
    "rsvp_closed_en": "RSVP is now closed — please contact us by phone below.",
}


# Old single-language keys → new bilingual keys (Khmer side keeps the old value)
_FIELD_MIGRATIONS = [
    ("groom_father", "groom_father_kh"),
    ("groom_mother", "groom_mother_kh"),
    ("bride_father", "bride_father_kh"),
    ("bride_mother", "bride_mother_kh"),
    ("time_display", "time_display_en"),
    # Old currency-only KHQR slots → groom's side of the new side-based slots
    ("khqr_usd", "khqr_groom_usd"),
    ("khqr_khr", "khqr_groom_khr"),
]


def load_content():
    content = dict(DEFAULT_CONTENT)
    data = storage.read_content()
    if data:
        for old_key, new_key in _FIELD_MIGRATIONS:
            if old_key in data and new_key not in data:
                data[new_key] = data[old_key]
        # Old standalone table dict → merged guest list
        if data.get("tables") and not data.get("guest_list"):
            data["guest_list"] = [{"name": k, "table": v} for k, v in data["tables"].items()]
        content.update(data)
    return content


def ext_of(filename):
    return filename.rsplit(".", 1)[1].lower() if "." in filename else ""


def compress_image(file_storage, max_width=1600, quality=82):
    """Re-encode an uploaded image as WebP, resized for fast mobile loading."""
    file_storage.stream.seek(0)
    img = Image.open(file_storage.stream)
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "RGBA"):
        # keep transparency for palette images that have it (e.g. PNG logos)
        has_alpha = img.mode == "LA" or (img.mode == "P" and "transparency" in img.info)
        img = img.convert("RGBA" if has_alpha else "RGB")
    if img.width > max_width:
        img = img.resize((max_width, round(img.height * max_width / img.width)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "WEBP", quality=quality)
    return buf.getvalue()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def locked(view):
    """Hold DATA_LOCK for the whole request so concurrent read-modify-write
    cycles on the JSON files can't drop each other's changes."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        with DATA_LOCK:
            return view(*args, **kwargs)
    return wrapped


def darken(hex_color, factor=0.8):
    """Derived darker shade of the admin-chosen theme color."""
    try:
        h = hex_color.lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, IndexError):
        return "#a8873a"
    return "#%02x%02x%02x" % tuple(int(v * factor) for v in (r, g, b))


def rsvp_is_open(c):
    """False once the admin-set RSVP deadline (end of that day, ICT) passes."""
    raw = (c.get("rsvp_deadline") or "").strip()
    if not raw:
        return True
    try:
        deadline = datetime.fromisoformat(raw)
    except ValueError:
        return True
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone(timedelta(hours=7)))
    if len(raw) == 10:  # date only → keep the form open through that day
        deadline += timedelta(days=1)
    return datetime.now(timezone.utc) < deadline


def youtube_embed(url):
    """Privacy-friendly embed URL from any common YouTube link format."""
    m = re.search(r"(?:youtu\.be/|v=|shorts/|embed/|live/)([\w-]{6,})", url or "")
    return f"https://www.youtube-nocookie.com/embed/{m.group(1)}" if m else None


def merged_section_order(c):
    """Saved order with unknown ids dropped and sections added after the save
    slotted into their default position (not dumped at the end)."""
    order = [s for s in c.get("section_order", []) if s in SECTION_IDS]
    for i, sid in enumerate(SECTION_IDS):
        if sid not in order:
            if i and SECTION_IDS[i - 1] in order:
                order.insert(order.index(SECTION_IDS[i - 1]) + 1, sid)
            else:
                order.append(sid)
    return order


def resolve_sections(c):
    hidden = set(c.get("section_hidden", []))
    return [s for s in merged_section_order(c) if s not in hidden]


def ensure_guest_ids(c):
    """Guests saved before short links existed get an id assigned once."""
    if any(not g.get("id") for g in c.get("guest_list", [])):
        with DATA_LOCK:
            for g in c["guest_list"]:
                if not g.get("id"):
                    g["id"] = uuid.uuid4().hex[:6]
            storage.write_content(c)


# Visit counter: counted in memory, flushed to storage every N views so we
# don't hammer the HF dataset with a commit per page load.
# Seeded from stats.json after storage.init() at the bottom of this file.
_visit_stats = {"visits": 0, "guests": {}}
_visit_lock = threading.Lock()
_visit_unflushed = 0


def record_visit(guest):
    global _visit_unflushed
    with _visit_lock:
        _visit_stats["visits"] += 1
        if guest:
            g = _visit_stats["guests"]
            g[guest] = g.get(guest, 0) + 1
        # daily buckets (ICT dates) for the visits-over-time chart
        daily = _visit_stats.setdefault("daily", {})
        today = datetime.now(timezone(timedelta(hours=7))).date().isoformat()
        daily[today] = daily.get(today, 0) + 1
        for old in sorted(daily)[:-30]:
            del daily[old]
        _visit_unflushed += 1
        if _visit_unflushed >= 20:
            _visit_unflushed = 0
            storage.write_json("stats.json", _visit_stats)


# Public-form flood protection. The limit is per IP but generous, because
# many guests at the venue will share one WiFi IP.
_form_hits = {}
_form_lock = threading.Lock()


def rate_limited(max_hits=20, window=300):
    """True when this IP has already submitted max_hits times in the window."""
    ip = request.remote_addr or "?"
    now = time.time()
    with _form_lock:
        hits = [t for t in _form_hits.get(ip, []) if now - t < window]
        if len(hits) >= max_hits:
            _form_hits[ip] = hits
            return True
        hits.append(now)
        _form_hits[ip] = hits
        if len(_form_hits) > 2000:  # prune idle IPs
            for stale in [k for k, v in _form_hits.items() if not v or now - v[-1] > window]:
                del _form_hits[stale]
    return False


def build_checklist(c):
    """Launch-readiness audit shown at the top of the admin panel.
    Each item: (label, ok, required)."""
    date_ok = False
    try:
        date_ok = datetime.fromisoformat(c["date_iso"]) > datetime.now(
            timezone(timedelta(hours=7)))
    except ValueError:
        pass
    return [
        ("Wedding date is valid and in the future", date_ok, True),
        ("Data persistence (HF sync) is ON", storage.hf_enabled(), True),
        ("Admin password changed from the default", ADMIN_PASSWORD != "admin123", True),
        ("Cover photo uploaded", bool(c.get("hero_photo")), True),
        ("Guest list saved", bool(c.get("guest_list")), True),
        ("Gallery has photos", bool(c.get("gallery")), False),
        ("KHQR gift code uploaded", any(c.get(f"khqr_{s}") for s in KHQR_SLOTS), False),
        ("Background music added", bool(c.get("music")), False),
        ("RSVP deadline set", bool(c.get("rsvp_deadline")), False),
        ("Telegram alerts configured", telegram_enabled(), False),
    ]


def time_ago(iso):
    """'3h ago' style label for the admin activity feed."""
    try:
        delta = datetime.now(timezone.utc) - datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return ""
    seconds = int(delta.total_seconds())
    if seconds < 3600:
        return f"{max(1, seconds // 60)}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def build_activity():
    """Newest guest activity across RSVPs, wishes and photo uploads."""
    events = []
    for r in storage.read_json("rsvp.json") or []:
        if r.get("attending") == "yes":
            text = f"{r.get('name')} — attending, {r.get('guests')} guest(s)"
        else:
            text = f"{r.get('name')} — can't attend"
        events.append((r.get("created_at", ""), "✅", text))
    for w in storage.read_json("wishes.json") or []:
        events.append((w.get("created_at", ""), "💬", f"Wish from {w.get('name')}"))
    for p in storage.read_json("guest_photos.json") or []:
        state = "approved" if p.get("approved") else "waiting for approval"
        events.append((p.get("created_at", ""), "📷",
                       f"Photo from {p.get('name') or 'a guest'} ({state})"))
    events.sort(reverse=True)
    return [{"icon": icon, "text": text, "ago": time_ago(ts)}
            for ts, icon, text in events[:12]]


def notify_telegram(text):
    """Fire-and-forget Telegram message to the couple when a guest responds.
    Enabled by setting TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat_id):
        return

    def _send():
        try:
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode(),
            )
            urllib.request.urlopen(req, timeout=10)
        except Exception as e:
            print(f"[telegram] Warning: could not send notification: {e}")

    threading.Thread(target=_send, daemon=True).start()


def telegram_enabled():
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def back_to_page(anchor):
    """Redirect to the public page, keeping the personalized ?to= guest name."""
    guest = request.form.get("to", "").strip()
    url = url_for("index", to=guest or None)
    return redirect(f"{url}#{anchor}")


# ---------- Public ----------

@app.route("/")
def index():
    c = load_content()
    wishes = storage.read_json("wishes.json") or []
    visible = [w for w in wishes if not w.get("hidden")]
    guest = request.args.get("to", "").strip()[:60]
    record_visit(guest)
    # Cache-buster for the og:image so Telegram refetches it after edits
    og_v = hashlib.md5("|".join([
        c.get("hero_photo", ""), c["groom_name_en"], c["bride_name_en"], c["date_en"],
    ]).encode("utf-8")).hexdigest()[:10]
    # Table lookup for personalized links (case-insensitive)
    tables = {g["name"].casefold(): g["table"]
              for g in c.get("guest_list", []) if g.get("table")}
    guest_table = tables.get(guest.casefold()) if guest else None
    # Hero slideshow: hero photo + first gallery photos
    slides = []
    if c.get("hero_slideshow") == "yes":
        slides = ([c["hero_photo"]] if c.get("hero_photo") else []) + list(c.get("gallery", []))[:4]
        if len(slides) < 2:
            slides = []
    guest_photos = [p for p in (storage.read_json("guest_photos.json") or []) if p.get("approved")]
    # Envelope intro background: hero + first gallery photos, crossfaded.
    # Gallery uses the small thumbs — they sit under a soft veil, and the
    # envelope is the first paint so it must load fast on mobile data.
    envelope_slides = []
    if c.get("show_envelope") == "yes":
        envelope_slides = (([c["hero_photo"]] if c.get("hero_photo") else [])
                           + [f"thumb_{g}" for g in c.get("gallery", [])])[:4]
    dress_colors = [col.strip() for col in c.get("dress_colors", "").split(",")
                    if re.fullmatch(r"#[0-9a-fA-F]{3,8}", col.strip())]
    sections = resolve_sections(c)
    if c.get("after_mode") == "yes":  # keepsake mode: the wedding has happened
        sections = [s for s in sections if s not in ("rsvp",)]
    voices = [v for v in (storage.read_json("voice_wishes.json") or []) if v.get("approved")]
    return render_template("index.html", c=c, wishes=list(reversed(visible))[:100],
                           voices=list(reversed(voices))[:30],
                           guest=guest, og_v=og_v, theme_dark=darken(c["theme_color"]),
                           sections=sections, rsvp_open=rsvp_is_open(c),
                           guest_table=guest_table, slides=slides,
                           envelope_slides=envelope_slides,
                           video_embed=youtube_embed(c.get("video_url")),
                           dress_colors=dress_colors,
                           guest_photos=list(reversed(guest_photos)))


@app.route("/g/<gid>")
def guest_link(gid):
    """Short personalized link — /g/ab12cd → the invitation greeting that guest."""
    for g in load_content().get("guest_list", []):
        if g.get("id") == gid:
            return redirect(url_for("index", to=g["name"]))
    return redirect(url_for("index"))


@app.route("/photos/<path:filename>")
def photos(filename):
    # Uploaded filenames are unique (timestamped), so they can be cached forever.
    resp = send_from_directory(storage.PHOTOS_DIR, filename)
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp


@app.route("/rsvp", methods=["POST"])
@locked
def rsvp():
    if request.form.get("website") or rate_limited():  # honeypot + flood guard
        return back_to_page("rsvp")
    if not rsvp_is_open(load_content()):
        return back_to_page("rsvp")
    name = request.form.get("name", "").strip()[:80]
    attending = "yes" if request.form.get("attending") == "yes" else "no"
    try:
        guests = max(1, min(20, int(request.form.get("guests", "1"))))
    except ValueError:
        guests = 1
    note = request.form.get("note", "").strip()[:300]
    companions = request.form.get("companions", "").strip()[:300]
    if name:
        items = storage.read_json("rsvp.json") or []
        entry = {
            "id": uuid.uuid4().hex,
            "name": name,
            "attending": attending,
            "guests": guests if attending == "yes" else 0,
            "companions": companions if attending == "yes" else "",
            "note": note,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        # Same guest answering again updates their RSVP instead of duplicating
        for i, r in enumerate(items):
            if r.get("name", "").strip().casefold() == name.casefold():
                entry["id"] = r.get("id", entry["id"])
                items[i] = entry
                break
        else:
            items.append(entry)
        storage.write_json("rsvp.json", items)
        flash("rsvp_ok", "toast")
        status = f"✅ Attending — {guests} guest(s)" if attending == "yes" else "❌ Can't attend"
        notify_telegram(f"💍 New RSVP\n{name}\n{status}" + (f"\nNote: {note}" if note else ""))
    return back_to_page("rsvp")


@app.route("/wishes", methods=["POST"])
@locked
def wishes():
    if request.form.get("website") or rate_limited():
        return back_to_page("wishes")
    name = request.form.get("name", "").strip()[:80]
    message = request.form.get("message", "").strip()[:500]
    if name and message:
        items = storage.read_json("wishes.json") or []
        items.append({
            "id": uuid.uuid4().hex,
            "name": name,
            "message": message,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        storage.write_json("wishes.json", items)
        flash("wish_ok", "toast")
        notify_telegram(f"💌 New wish\n{name}:\n{message}")
    return back_to_page("wishes")


@app.route("/upload-guest-photo", methods=["POST"])
@locked
def upload_guest_photo():
    c = load_content()
    if c.get("guest_upload") != "yes" or request.form.get("website") or rate_limited():
        return back_to_page("guest-photos")
    name = request.form.get("name", "").strip()[:80]
    items = storage.read_json("guest_photos.json") or []
    saved = 0
    for file in request.files.getlist("photos")[:3]:
        if file and file.filename and ext_of(file.filename) in IMAGE_EXTENSIONS:
            try:
                data = compress_image(file, max_width=1600)
            except Exception:
                continue
            filename = f"gp_{int(time.time())}_{uuid.uuid4().hex[:6]}.webp"
            storage.save_bytes(data, filename)
            items.append({
                "id": uuid.uuid4().hex,
                "file": filename,
                "name": name,
                "approved": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            saved += 1
    if saved:
        storage.write_json("guest_photos.json", items)
        flash("upload_ok", "toast")
        notify_telegram(f"📷 {name or 'A guest'} sent {saved} photo(s) — approve them in /admin")
    return back_to_page("guest-photos")


@app.route("/api/wishes")
def api_wishes():
    """Visible wishes as JSON — polled by the page for the live wishes wall."""
    wishes = storage.read_json("wishes.json") or []
    visible = [{"id": w.get("id", ""), "name": w.get("name", ""),
                "message": w.get("message", ""), "hearts": w.get("hearts", 0)}
               for w in reversed(wishes) if not w.get("hidden")][:100]
    return {"wishes": visible}


@app.route("/wish-heart", methods=["POST"])
@locked
def wish_heart():
    """Guests tap ❤ on a wish. Synced to the dataset every few hearts so a
    lively reception doesn't create a commit per tap."""
    if rate_limited(max_hits=60, window=300):
        return {"hearts": None}, 429
    items = storage.read_json("wishes.json") or []
    for w in items:
        if w.get("id") == request.form.get("id"):
            w["hearts"] = int(w.get("hearts", 0)) + 1
            storage.write_json("wishes.json", items, push=w["hearts"] % 5 == 0)
            return {"hearts": w["hearts"]}
    return {"hearts": None}, 404


@app.route("/upload-voice", methods=["POST"])
@locked
def upload_voice():
    """Guest voice blessing — moderated like guest photos."""
    c = load_content()
    if c.get("voice_wishes") != "yes" or rate_limited(max_hits=6, window=300):
        return {"ok": False}, 403
    file = request.files.get("audio")
    if not file:
        return {"ok": False}, 400
    data = file.read()
    if not data or len(data) > 5 * 1024 * 1024:
        return {"ok": False}, 400
    ext = "mp4" if "mp4" in (file.mimetype or "") else "webm"
    filename = f"voice_{int(time.time())}_{uuid.uuid4().hex[:6]}.{ext}"
    storage.save_bytes(data, filename)
    items = storage.read_json("voice_wishes.json") or []
    items.append({
        "id": uuid.uuid4().hex,
        "file": filename,
        "name": request.form.get("name", "").strip()[:80],
        "approved": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    storage.write_json("voice_wishes.json", items)
    notify_telegram(f"🎙 Voice blessing from {request.form.get('name') or 'a guest'} "
                    "— approve it in /admin")
    return {"ok": True}


@app.route("/admin/voice", methods=["POST"])
@login_required
@locked
def moderate_voice():
    action = request.form.get("action", "")
    items = storage.read_json("voice_wishes.json") or []
    for v in items:
        if v.get("id") == request.form.get("id"):
            if action == "approve":
                v["approved"] = True
                flash("Voice blessing approved.", "success")
            elif action == "delete":
                storage.delete_photo(v.get("file", ""))
                items.remove(v)
                flash("Voice blessing deleted.", "success")
            storage.write_json("voice_wishes.json", items)
            break
    return redirect(url_for("admin") + "#voice-admin")


@app.route("/wall")
def wall():
    """Full-screen projection page for the reception: live wishes + QR."""
    c = load_content()
    return render_template("wall.html", c=c, theme_dark=darken(c["theme_color"]))


@app.route("/wall-qr.png")
def wall_qr():
    import qrcode
    img = qrcode.make(request.url_root + "#wishes", box_size=10, border=2).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return Response(buf.getvalue(), mimetype="image/png",
                    headers={"Cache-Control": "public, max-age=3600"})


# Cache-and-network service worker so the invitation survives weak signal
_SW_JS = """
const CACHE = 'wedding-%s';
self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))));
});
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);
  if (url.origin !== location.origin) return;
  e.respondWith(
    fetch(e.request).then(resp => {
      if (resp.ok) {
        const copy = resp.clone();
        caches.open(CACHE).then(c => c.put(e.request, copy));
      }
      return resp;
    }).catch(() => caches.match(e.request))
  );
});
"""


@app.route("/sw.js")
def service_worker():
    return Response(_SW_JS % ASSET_V, mimetype="application/javascript",
                    headers={"Cache-Control": "no-cache"})


@app.route("/manifest.json")
def manifest():
    c = load_content()
    return {
        "name": f"{c['groom_name_en']} & {c['bride_name_en']} — Wedding",
        "short_name": "Wedding 💍",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#fdf9f2",
        "theme_color": c.get("theme_color", "#c9a84c"),
        "icons": [
            {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    }


# Rendered og:image cache — regenerated when hero/names/date change
_og_cache = {"key": None, "jpeg": None}
_FONTS_DIR = os.path.join(os.path.dirname(__file__), "static", "fonts")


@app.route("/og.jpg")
def og_image():
    """1200x630 social preview card: hero photo + couple names + date."""
    c = load_content()
    key = (c.get("hero_photo", ""), c["groom_name_en"], c["bride_name_en"], c["date_en"])
    if _og_cache["key"] != key:
        W, H = 1200, 630
        hero = c.get("hero_photo")
        hero_path = storage.PHOTOS_DIR / hero if hero else None
        if hero_path and hero_path.exists():
            img = Image.open(hero_path).convert("RGB")
            img = ImageOps.fit(img, (W, H), Image.LANCZOS)
        else:
            img = Image.new("RGB", (W, H), (246, 236, 217))
        # darken the lower half so the text reads over any photo
        overlay = Image.new("L", (1, H))
        overlay.putdata([min(200, max(0, int((y / H - 0.35) * 320))) for y in range(H)])
        img.paste((20, 15, 8), (0, 0, W, H), overlay.resize((W, H)))
        draw = ImageDraw.Draw(img)
        names = f"{c['groom_name_en']}  &  {c['bride_name_en']}"
        try:
            f_names = ImageFont.truetype(os.path.join(_FONTS_DIR, "GreatVibes-Regular.ttf"), 92)
            f_date = ImageFont.truetype(os.path.join(_FONTS_DIR, "PlayfairDisplay.ttf"), 40)
        except OSError:
            f_names = f_date = ImageFont.load_default()
        for text, font, y in ((names, f_names, 415), (c["date_en"], f_date, 540)):
            w = draw.textlength(text, font=font)
            draw.text(((W - w) / 2, y), text, font=font, fill=(250, 243, 226))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=88)
        _og_cache.update(key=key, jpeg=buf.getvalue())
    return Response(_og_cache["jpeg"], mimetype="image/jpeg",
                    headers={"Cache-Control": "public, max-age=3600"})


@app.route("/calendar.ics")
def calendar_ics():
    """Downloadable calendar event so guests can save the wedding date."""
    c = load_content()
    try:
        start = datetime.fromisoformat(c["date_iso"])
    except ValueError:
        return redirect(url_for("index"))
    end = start + timedelta(hours=5)
    fmt = "%Y%m%dT%H%M%SZ"
    esc = lambda s: s.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")
    location = f"{c['venue_name_en']}, {c['venue_address_en']}"
    ics = "\r\n".join([
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//wedding-invite//EN",
        "BEGIN:VEVENT",
        f"UID:wedding-{hashlib.md5(c['date_iso'].encode()).hexdigest()[:12]}",
        f"DTSTAMP:{datetime.now(timezone.utc).strftime(fmt)}",
        f"DTSTART:{start.astimezone(timezone.utc).strftime(fmt)}",
        f"DTEND:{end.astimezone(timezone.utc).strftime(fmt)}",
        f"SUMMARY:{esc('Wedding of ' + c['groom_name_en'] + ' & ' + c['bride_name_en'])} 💍",
        f"LOCATION:{esc(location)}",
        f"DESCRIPTION:{esc(c['invite_en'])}",
        "END:VEVENT",
        "END:VCALENDAR",
        "",
    ])
    return Response(ics, mimetype="text/calendar",
                    headers={"Content-Disposition": "attachment; filename=wedding.ics"})


# ---------- Auth ----------

# Per-IP login throttle: 5 wrong passwords locks the IP out for 60 seconds.
_login_failures = {}


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # Cap memory: drop expired/idle entries once the table gets large
        if len(_login_failures) >= 1000:
            now = time.time()
            for stale in [k for k, v in _login_failures.items() if v[1] <= now]:
                del _login_failures[stale]
        ip = request.remote_addr or "?"
        fails, locked_until = _login_failures.get(ip, (0, 0.0))
        if time.time() < locked_until:
            flash("Too many attempts. Please wait a minute and try again.", "error")
            return render_template("login.html")
        if secrets.compare_digest(request.form.get("password", ""), ADMIN_PASSWORD):
            _login_failures.pop(ip, None)
            session["logged_in"] = True
            notify_telegram(f"🔐 Admin login from IP {ip}")
            return redirect(url_for("admin"))
        fails += 1
        _login_failures[ip] = (0, time.time() + 60) if fails >= 5 else (fails, 0.0)
        flash("Incorrect password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ---------- Admin ----------

@app.route("/admin")
@login_required
def admin():
    c = load_content()
    rsvps = storage.read_json("rsvp.json") or []
    wishes_list = storage.read_json("wishes.json") or []
    attending = [r for r in rsvps if r.get("attending") == "yes"]
    stats = {
        "yes": len(attending),
        "no": len(rsvps) - len(attending),
        "guests": sum(r.get("guests", 0) for r in attending),
    }
    ensure_guest_ids(c)
    guest_photos = storage.read_json("guest_photos.json") or []
    with _visit_lock:
        visit_stats = {"visits": _visit_stats["visits"],
                       "unique_guests": len(_visit_stats["guests"])}
    # Sections in their saved order (new ones slotted in) for the design panel
    label_map = dict(SECTION_LABELS)
    admin_sections = [(s, label_map[s]) for s in merged_section_order(c)]
    def guest_line(g):
        if g.get("group"):
            return f"{g['name']} = {g.get('table', '')} = {g['group']}"
        if g.get("table"):
            return f"{g['name']} = {g['table']}"
        return g["name"]

    guest_rows = build_guest_rows(c)
    groups = sorted({g["group"] for g in guest_rows if g["group"]})
    helper_link = url_for("checkin_helper", token=ensure_checkin_token(c), _external=True)
    gifts = storage.read_json("gifts.json") or []

    def gift_total(cur):
        total = 0.0
        for g in gifts:
            if g.get("currency") == cur:
                try:
                    total += float(str(g.get("amount", "0")).replace(",", ""))
                except ValueError:
                    pass
        return f"{total:,.0f}"

    with _visit_lock:
        daily = dict(_visit_stats.get("daily", {}))
    today = datetime.now(timezone(timedelta(hours=7))).date()
    chart = []
    for i in range(13, -1, -1):
        day = (today - timedelta(days=i)).isoformat()
        chart.append({"day": day[5:], "count": daily.get(day, 0)})
    chart_max = max([c_["count"] for c_ in chart] + [1])
    voice_items = storage.read_json("voice_wishes.json") or []
    return render_template("admin.html", c=c, field_groups=FIELD_GROUPS,
                           checklist=build_checklist(c), activity=build_activity(),
                           hf_enabled=storage.hf_enabled(), tg_enabled=telegram_enabled(),
                           rsvps=list(reversed(rsvps)), wishes=list(reversed(wishes_list)),
                           stats=stats, visit_stats=visit_stats,
                           theme_presets=THEME_PRESETS, kh_fonts=KH_HEADING_FONTS,
                           script_fonts=SCRIPT_FONTS, admin_sections=admin_sections,
                           guest_photos=list(reversed(guest_photos)),
                           guest_rows=guest_rows, guest_groups=groups,
                           helper_link=helper_link,
                           gifts=list(reversed(gifts)),
                           gift_totals={"USD": gift_total("USD"), "KHR": gift_total("KHR")},
                           chart=chart, chart_max=chart_max,
                           voice_items=list(reversed(voice_items)),
                           guest_list_text="\n".join(
                               guest_line(g) for g in c.get("guest_list", [])))


@app.route("/admin/save-text", methods=["POST"])
@login_required
@locked
def save_text():
    content = load_content()
    for key, _, _ in FIELDS:
        if key in request.form:
            content[key] = request.form[key].strip()
    # Schedule rows arrive as parallel arrays
    times = request.form.getlist("schedule_time")
    titles_kh = request.form.getlist("schedule_title_kh")
    titles_en = request.form.getlist("schedule_title_en")
    content["schedule"] = [
        {"time": t.strip(), "title_kh": k.strip(), "title_en": e.strip()}
        for t, k, e in zip(times, titles_kh, titles_en)
        if t.strip() or k.strip() or e.strip()
    ]
    content["story"] = [
        {"time": t.strip(), "title_kh": k.strip(), "title_en": e.strip()}
        for t, k, e in zip(request.form.getlist("story_time"),
                           request.form.getlist("story_title_kh"),
                           request.form.getlist("story_title_en"))
        if t.strip() or k.strip() or e.strip()
    ]
    content["faq"] = [
        {"q_kh": qk.strip(), "q_en": qe.strip(), "a_kh": ak.strip(), "a_en": ae.strip()}
        for qk, qe, ak, ae in zip(request.form.getlist("faq_q_kh"),
                                  request.form.getlist("faq_q_en"),
                                  request.form.getlist("faq_a_kh"),
                                  request.form.getlist("faq_a_en"))
        if qk.strip() or qe.strip() or ak.strip() or ae.strip()
    ]
    storage.write_content(content)
    flash("Text saved successfully.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/upload-hero", methods=["POST"])
@login_required
@locked
def upload_hero():
    file = request.files.get("photo")
    if not file or not file.filename:
        flash("No file selected.", "error")
    elif ext_of(file.filename) not in IMAGE_EXTENSIONS:
        flash("Only JPG, PNG, WEBP or GIF images are allowed.", "error")
    else:
        try:
            data = compress_image(file, max_width=1920)
        except Exception:
            flash("Could not read that image file.", "error")
            return redirect(url_for("admin"))
        filename = f"hero_{int(time.time())}.webp"
        content = load_content()
        old = content.get("hero_photo")
        storage.save_bytes(data, filename)
        content["hero_photo"] = filename
        storage.write_content(content)
        if old:
            storage.delete_photo(old)
        flash("Cover photo updated.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/upload-bg", methods=["POST"])
@login_required
@locked
def upload_bg():
    file = request.files.get("photo")
    if not file or not file.filename:
        flash("No file selected.", "error")
    elif ext_of(file.filename) not in IMAGE_EXTENSIONS:
        flash("Only JPG, PNG, WEBP or GIF images are allowed.", "error")
    else:
        try:
            # Lower quality is fine here — it sits behind a soft overlay.
            data = compress_image(file, max_width=1920, quality=75)
        except Exception:
            flash("Could not read that image file.", "error")
            return redirect(url_for("admin"))
        filename = f"bg_{int(time.time())}.webp"
        content = load_content()
        old = content.get("bg_photo")
        storage.save_bytes(data, filename)
        content["bg_photo"] = filename
        storage.write_content(content)
        if old:
            storage.delete_photo(old)
        flash("Page background updated.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/upload-gallery", methods=["POST"])
@login_required
@locked
def upload_gallery():
    files = request.files.getlist("photos")
    content = load_content()
    saved = 0
    for file in files:
        if file and file.filename and ext_of(file.filename) in IMAGE_EXTENSIONS:
            try:
                data = compress_image(file, max_width=1600)
                thumb = compress_image(file, max_width=480, quality=78)
            except Exception:
                continue
            filename = f"g_{int(time.time())}_{saved}_{uuid.uuid4().hex[:6]}.webp"
            storage.save_bytes(data, filename)
            storage.save_bytes(thumb, f"thumb_{filename}")
            content.setdefault("gallery", []).append(filename)
            saved += 1
    if saved:
        storage.write_content(content)
        flash(f"Uploaded {saved} photo(s).", "success")
    else:
        flash("No valid images were selected.", "error")
    return redirect(url_for("admin"))


KHQR_SLOTS = {"groom_usd", "groom_khr", "bride_usd", "bride_khr"}


@app.route("/admin/upload-khqr", methods=["POST"])
@login_required
@locked
def upload_khqr():
    slot = request.form.get("slot", "")
    key = f"khqr_{slot}" if slot in KHQR_SLOTS else None
    file = request.files.get("photo")
    if not key:
        flash("Unknown KHQR slot.", "error")
    elif not file or not file.filename:
        flash("No file selected.", "error")
    elif ext_of(file.filename) not in IMAGE_EXTENSIONS:
        flash("Only image files are allowed.", "error")
    else:
        # QR codes are saved as-is (no compression) so they stay sharp and scannable
        filename = f"khqr_{slot}_{int(time.time())}.{ext_of(file.filename)}"
        content = load_content()
        old = content.get(key)
        storage.save_photo(file, filename)
        content[key] = filename
        storage.write_content(content)
        if old:
            storage.delete_photo(old)
        flash(f"KHQR ({slot.replace('_', ' ').upper()}) updated.", "success")
    return redirect(url_for("admin") + "#khqr")


@app.route("/admin/upload-music", methods=["POST"])
@login_required
@locked
def upload_music():
    file = request.files.get("music")
    if not file or not file.filename:
        flash("No file selected.", "error")
    elif ext_of(file.filename) not in AUDIO_EXTENSIONS:
        flash("Only MP3, M4A, OGG or WAV audio is allowed.", "error")
    else:
        filename = f"music_{int(time.time())}.{ext_of(file.filename)}"
        content = load_content()
        old = content.get("music")
        storage.save_photo(file, filename)
        content["music"] = filename
        storage.write_content(content)
        if old:
            storage.delete_photo(old)
        flash("Background music updated.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/upload-video", methods=["POST"])
@login_required
@locked
def upload_video():
    file = request.files.get("video")
    if not file or not file.filename:
        flash("No file selected.", "error")
    elif ext_of(file.filename) not in VIDEO_EXTENSIONS:
        flash("Only MP4, WEBM, MOV or M4V video is allowed.", "error")
    else:
        filename = f"video_{int(time.time())}.{ext_of(file.filename)}"
        content = load_content()
        old = content.get("video")
        storage.save_photo(file, filename)
        content["video"] = filename
        storage.write_content(content)
        if old:
            storage.delete_photo(old)
        flash("Video uploaded.", "success")
    return redirect(url_for("admin") + "#video-admin")


@app.route("/admin/backup.zip")
@login_required
def backup():
    """Everything — settings, guest list, RSVPs, wishes, photos — in one ZIP."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in ("content.json", "rsvp.json", "wishes.json",
                     "guest_photos.json", "stats.json"):
            path = storage.DATA_DIR / name
            if path.exists():
                z.write(path, name)
        if storage.PHOTOS_DIR.exists():
            for path in storage.PHOTOS_DIR.iterdir():
                if path.is_file():
                    z.write(path, f"photos/{path.name}")
    fname = f"wedding-backup-{datetime.now(timezone.utc):%Y%m%d}.zip"
    return Response(buf.getvalue(), mimetype="application/zip",
                    headers={"Content-Disposition": f"attachment; filename={fname}"})


@app.route("/admin/restore", methods=["POST"])
@login_required
@locked
def restore():
    """Put a downloaded backup ZIP back — overwrites current data."""
    file = request.files.get("backup")
    if not file or not file.filename.lower().endswith(".zip"):
        flash("Please choose a backup .zip file.", "error")
        return redirect(url_for("admin") + "#backup-card")
    try:
        z = zipfile.ZipFile(file.stream)
    except zipfile.BadZipFile:
        flash("That file is not a valid backup ZIP.", "error")
        return redirect(url_for("admin") + "#backup-card")
    media_exts = IMAGE_EXTENSIONS | AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
    restored_data, restored_media = 0, 0
    for name in z.namelist():
        if name in ("content.json", "rsvp.json", "wishes.json",
                    "guest_photos.json", "stats.json"):
            try:
                data = json.loads(z.read(name).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            storage.write_json(name, data)
            restored_data += 1
        elif name.startswith("photos/") and not name.endswith("/"):
            fname = os.path.basename(name)  # no path traversal
            if fname and ext_of(fname) in media_exts:
                storage.save_bytes(z.read(name), fname)
                restored_media += 1
    if restored_data:
        saved = storage.read_json("stats.json")
        if saved:
            with _visit_lock:
                _visit_stats.update(visits=saved.get("visits", 0),
                                    guests=saved.get("guests", {}))
    flash(f"Restore complete — {restored_data} data file(s), "
          f"{restored_media} photo/media file(s).", "success")
    return redirect(url_for("admin"))


def ensure_checkin_token(c):
    """Secret token so a reception-desk helper can use check-in without the
    admin password."""
    if not c.get("checkin_token"):
        with DATA_LOCK:
            c["checkin_token"] = uuid.uuid4().hex[:12]
            storage.write_content(c)
    return c["checkin_token"]


def render_checkin(c, token=None):
    ensure_guest_ids(c)
    rsvps = storage.read_json("rsvp.json") or []
    attending = {r.get("name", "").strip().casefold(): r
                 for r in rsvps if r.get("attending") == "yes"}
    guests = []
    for g in c.get("guest_list", []):
        r = attending.get(g["name"].casefold())
        guests.append({"id": g.get("id", ""), "name": g["name"],
                       "table": g.get("table", ""), "group": g.get("group", ""),
                       "arrived": bool(g.get("arrived")),
                       "expected": r.get("guests") if r else None,
                       "companions": r.get("companions", "") if r else ""})
    return render_template("checkin.html", guests=guests, token=token,
                           arrived=sum(1 for g in guests if g["arrived"]),
                           total=len(guests))


@app.route("/admin/checkin")
@login_required
def checkin():
    """Wedding-day reception page: search guests, see tables, mark arrivals."""
    return render_checkin(load_content())


@app.route("/checkin/<token>")
def checkin_helper(token):
    c = load_content()
    if token != ensure_checkin_token(c):
        return redirect(url_for("index"))
    return render_checkin(c, token=token)


@app.route("/admin/checkin-toggle", methods=["POST"])
@locked
def checkin_toggle():
    content = load_content()
    token_ok = (request.form.get("token")
                and request.form.get("token") == content.get("checkin_token"))
    if not (session.get("logged_in") or token_ok):
        return {"error": "not allowed"}, 403
    for g in content.get("guest_list", []):
        if g.get("id") == request.form.get("id"):
            g["arrived"] = not g.get("arrived")
            storage.write_content(content)
            return {"arrived": g["arrived"]}
    return {"error": "unknown guest"}, 404


@app.route("/admin/remove-file", methods=["POST"])
@login_required
@locked
def remove_file():
    key = request.form.get("key", "")
    if key not in ("khqr_groom_usd", "khqr_groom_khr", "khqr_bride_usd",
                   "khqr_bride_khr", "music", "hero_photo", "bg_photo", "video"):
        flash("Unknown item.", "error")
        return redirect(url_for("admin"))
    content = load_content()
    filename = content.get(key)
    if filename:
        content[key] = ""
        storage.write_content(content)
        storage.delete_photo(filename)
        flash("Removed.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/move-photo", methods=["POST"])
@login_required
@locked
def move_photo():
    """Reorder a gallery photo one step up or down."""
    filename = request.form.get("filename", "")
    step = -1 if request.form.get("dir") == "up" else 1
    content = load_content()
    gallery = content.get("gallery", [])
    if filename in gallery:
        i = gallery.index(filename)
        j = i + step
        if 0 <= j < len(gallery):
            gallery[i], gallery[j] = gallery[j], gallery[i]
            storage.write_content(content)
    return redirect(url_for("admin") + "#gallery")


@app.route("/admin/delete-photo", methods=["POST"])
@login_required
@locked
def delete_photo():
    filename = request.form.get("filename", "")
    content = load_content()
    if filename in content.get("gallery", []):
        content["gallery"].remove(filename)
        storage.write_content(content)
        storage.delete_photo(filename)
        storage.delete_photo(f"thumb_{filename}")
        flash("Photo deleted.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/delete-rsvp", methods=["POST"])
@login_required
@locked
def delete_rsvp():
    items = storage.read_json("rsvp.json") or []
    items = [r for r in items if r.get("id") != request.form.get("id")]
    storage.write_json("rsvp.json", items)
    flash("RSVP deleted.", "success")
    return redirect(url_for("admin") + "#rsvps")


@app.route("/admin/save-design", methods=["POST"])
@login_required
@locked
def save_design():
    content = load_content()
    f = request.form
    color = f.get("theme_color", "").strip()
    if len(color) == 7 and color.startswith("#"):
        try:
            int(color[1:], 16)
            content["theme_color"] = color.lower()
        except ValueError:
            pass
    try:
        content["bg_overlay"] = str(min(0.95, max(0.0, float(f.get("bg_overlay", 0.25)))))
    except ValueError:
        pass
    if f.get("font_kh_heading") in KH_HEADING_FONTS:
        content["font_kh_heading"] = f["font_kh_heading"]
    if f.get("font_en_script") in SCRIPT_FONTS:
        content["font_en_script"] = f["font_en_script"]
    petal = f.get("petal_emoji", "").strip()
    content["petal_emoji"] = petal[:8] if petal else "🌸"
    try:
        content["petal_count"] = str(min(20, max(0, int(f.get("petal_count", 5)))))
    except ValueError:
        pass
    for key in ("show_envelope", "hero_slideshow", "guest_upload",
                "voice_wishes", "after_mode"):
        content[key] = "yes" if f.get(key) else "no"
    if f.get("default_lang") in ("kh", "en"):
        content["default_lang"] = f["default_lang"]
    deadline = f.get("rsvp_deadline", "").strip()
    if deadline:
        try:
            datetime.fromisoformat(deadline)
        except ValueError:
            deadline = content.get("rsvp_deadline", "")
    content["rsvp_deadline"] = deadline
    order = [s for s in f.get("section_order", "").split(",") if s in SECTION_IDS]
    if order:
        content["section_order"] = order + [s for s in SECTION_IDS if s not in order]
    content["section_hidden"] = [s for s in f.getlist("section_hidden") if s in SECTION_IDS]
    storage.write_content(content)
    flash("Design & feature settings saved.", "success")
    return redirect(url_for("admin") + "#design")


def build_guest_rows(c):
    """Per-guest link, template message, Telegram share URL and live status
    (opened the link? RSVP'd?) for the admin guest list."""
    rsvps = storage.read_json("rsvp.json") or []
    rsvp_by_name = {r.get("name", "").strip().casefold(): r for r in rsvps}
    with _visit_lock:
        opened = {k.strip().casefold() for k in _visit_stats["guests"]}
    base = request.url_root

    def render_msg(template, name, link):
        msg = template.replace("{name}", name).replace("{link}", link)
        if "{link}" not in template:  # never send a message without the link
            msg += "\n" + link
        return msg

    def tg_share(template, name, link):
        text = template.replace("{name}", name).replace("{link}", "").strip()
        return ("https://t.me/share/url?url=" + urllib.parse.quote(link)
                + "&text=" + urllib.parse.quote(text))

    invite_t = c.get("invite_template", "")
    remind_t = c.get("remind_template", "")
    thanks_t = c.get("thanks_template", "")
    rows = []
    for g in c.get("guest_list", []):
        name = g["name"]
        # Short link when the guest has an id; long ?to= form as fallback
        link = (base + "g/" + g["id"]) if g.get("id") else (base + "?to=" + urllib.parse.quote(name))
        rows.append({
            "name": name,
            "table": g.get("table", ""),
            "group": g.get("group", ""),
            "link": link,
            "msg": render_msg(invite_t, name, link),
            "remind": render_msg(remind_t, name, link),
            "thanks": render_msg(thanks_t, name, link),
            "tg": tg_share(invite_t, name, link),
            "tgr": tg_share(remind_t, name, link),
            "tgt": tg_share(thanks_t, name, link),
            "qr": url_for("guest_qr", name=name),
            "opened": name.casefold() in opened,
            "rsvp": rsvp_by_name.get(name.casefold()),
        })
    return rows


@app.route("/admin/save-guests", methods=["POST"])
@login_required
@locked
def save_guests():
    content = load_content()
    template = request.form.get("invite_template", "").strip()
    content["invite_template"] = template or DEFAULT_CONTENT["invite_template"]
    remind = request.form.get("remind_template", "").strip()
    content["remind_template"] = remind or DEFAULT_CONTENT["remind_template"]
    thanks = request.form.get("thanks_template", "").strip()
    content["thanks_template"] = thanks or DEFAULT_CONTENT["thanks_template"]
    # Keep short-link ids and check-in state stable across saves (matched by name)
    old = {g["name"].casefold(): g for g in content.get("guest_list", [])}
    guest_list, seen = [], set()
    for line in request.form.get("guest_list", "").splitlines():
        # "Name" or "Name = Table" or "Name = Table = Group"
        parts = [p.strip() for p in line.strip().split("=")]
        name = parts[0][:80]
        table = parts[1][:20] if len(parts) > 1 else ""
        group = parts[2][:30] if len(parts) > 2 else ""
        if name and name.casefold() not in seen:
            seen.add(name.casefold())
            prev = old.get(name.casefold(), {})
            guest_list.append({"name": name, "table": table, "group": group,
                               "id": prev.get("id") or uuid.uuid4().hex[:6],
                               "arrived": bool(prev.get("arrived"))})
    content["guest_list"] = guest_list
    storage.write_content(content)
    flash(f"Guest list saved — {len(guest_list)} guest(s).", "success")
    return redirect(url_for("admin") + "#guest-links")


@app.route("/admin/guest-qr")
@login_required
def guest_qr():
    """QR code of one guest's personalized link, for printed cards."""
    import qrcode
    name = request.args.get("name", "").strip()[:80]
    # Use the guest's short link when they have one — same URL as everywhere else
    gid = next((g.get("id") for g in load_content().get("guest_list", [])
                if g["name"].casefold() == name.casefold()), None)
    if gid:
        link = request.url_root + "g/" + gid
    else:
        link = request.url_root + ("?to=" + urllib.parse.quote(name) if name else "")
    img = qrcode.make(link, box_size=10, border=2).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    fname = urllib.parse.quote(f"qr-{name or 'guest'}.png")
    return Response(buf.getvalue(), mimetype="image/png",
                    headers={"Content-Disposition":
                             f"attachment; filename=guest-qr.png; filename*=UTF-8''{fname}"})


@app.route("/admin/save-gift", methods=["POST"])
@login_required
@locked
def save_gift():
    """Gift ledger (កត់ត្រាចងដៃ): record what each guest gave."""
    name = request.form.get("name", "").strip()[:80]
    amount = request.form.get("amount", "").strip()[:30]
    currency = request.form.get("currency", "USD")
    if currency not in ("USD", "KHR", "Gift"):
        currency = "USD"
    note = request.form.get("note", "").strip()[:200]
    if name and (amount or note):
        items = storage.read_json("gifts.json") or []
        items.append({
            "id": uuid.uuid4().hex,
            "name": name,
            "amount": amount,
            "currency": currency,
            "note": note,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        storage.write_json("gifts.json", items)
        flash("Gift recorded.", "success")
    else:
        flash("A name plus an amount or note is required.", "error")
    return redirect(url_for("admin") + "#gifts")


@app.route("/admin/delete-gift", methods=["POST"])
@login_required
@locked
def delete_gift():
    items = storage.read_json("gifts.json") or []
    items = [g for g in items if g.get("id") != request.form.get("id")]
    storage.write_json("gifts.json", items)
    flash("Gift entry deleted.", "success")
    return redirect(url_for("admin") + "#gifts")


@app.route("/admin/export-gifts")
@login_required
def export_gifts():
    items = storage.read_json("gifts.json") or []
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Name", "Amount", "Currency", "Note", "Recorded (UTC)"])
    for g in items:
        writer.writerow([g.get("name", ""), g.get("amount", ""), g.get("currency", ""),
                         g.get("note", ""), (g.get("created_at", "") or "")[:16].replace("T", " ")])
    return Response("\ufeff" + buf.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=wedding-gifts.csv"})


@app.route("/admin/export-guests")
@login_required
def export_guests():
    c = load_content()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Name", "Table", "Group", "Link", "Opened", "RSVP", "Guests", "Companions"])
    for g in build_guest_rows(c):
        rsvp = g["rsvp"]
        writer.writerow([
            g["name"], g["table"], g["group"], g["link"],
            "Yes" if g["opened"] else "No",
            ("Attending" if rsvp.get("attending") == "yes" else "Declined") if rsvp else "—",
            rsvp.get("guests", "") if rsvp else "",
            rsvp.get("companions", "") if rsvp else "",
        ])
    return Response("\ufeff" + buf.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=wedding-guests.csv"})


@app.route("/admin/guest-photo", methods=["POST"])
@login_required
@locked
def moderate_guest_photo():
    action = request.form.get("action", "")
    photo_id = request.form.get("id", "")
    items = storage.read_json("guest_photos.json") or []
    for p in items:
        if p.get("id") == photo_id:
            if action == "approve":
                p["approved"] = True
                flash("Photo approved — now visible on the page.", "success")
            elif action == "delete":
                storage.delete_photo(p.get("file", ""))
                items.remove(p)
                flash("Photo deleted.", "success")
            storage.write_json("guest_photos.json", items)
            break
    return redirect(url_for("admin") + "#guest-photo-admin")


@app.route("/admin/poster.png")
@login_required
def poster():
    """Print-ready poster with a QR code linking to the invitation."""
    import qrcode
    c = load_content()
    W, H = 1240, 1754  # A4 at 150 dpi
    cream, gold, ink = (253, 249, 242), (169, 135, 58), (58, 50, 38)
    img = Image.new("RGB", (W, H), cream)
    draw = ImageDraw.Draw(img)
    draw.rectangle([40, 40, W - 40, H - 40], outline=gold, width=4)
    draw.rectangle([56, 56, W - 56, H - 56], outline=gold, width=2)
    try:
        f_script = ImageFont.truetype(os.path.join(_FONTS_DIR, "GreatVibes-Regular.ttf"), 110)
        f_serif = ImageFont.truetype(os.path.join(_FONTS_DIR, "PlayfairDisplay.ttf"), 48)
        f_small = ImageFont.truetype(os.path.join(_FONTS_DIR, "PlayfairDisplay.ttf"), 34)
    except OSError:
        f_script = f_serif = f_small = ImageFont.load_default()
    def center(text, font, y, fill):
        draw.text(((W - draw.textlength(text, font=font)) / 2, y), text, font=font, fill=fill)
    center(c["groom_name_en"], f_script, 200, ink)
    center("&", f_script, 360, gold)
    center(c["bride_name_en"], f_script, 520, ink)
    center(c["date_en"], f_serif, 740, gold)
    center(c["venue_name_en"], f_small, 830, ink)
    qr = qrcode.make(request.url_root, box_size=10, border=2).convert("RGB")
    qr = qr.resize((520, 520))
    img.paste(qr, ((W - 520) // 2, 960))
    center("Scan to open the invitation", f_small, 1540, ink)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return Response(buf.getvalue(), mimetype="image/png",
                    headers={"Content-Disposition": "attachment; filename=wedding-poster.png"})


@app.route("/admin/export-rsvps")
@login_required
def export_rsvps():
    items = storage.read_json("rsvp.json") or []
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Name", "Attending", "Guests", "Companions", "Note", "Submitted (UTC)"])
    for r in items:
        writer.writerow([
            r.get("name", ""),
            "Yes" if r.get("attending") == "yes" else "No",
            r.get("guests", 0),
            r.get("companions", ""),
            r.get("note", ""),
            (r.get("created_at", "") or "")[:16].replace("T", " "),
        ])
    # BOM so Excel opens the Khmer names as UTF-8
    return Response("\ufeff" + buf.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=wedding-rsvps.csv"})


@app.route("/admin/toggle-wish", methods=["POST"])
@login_required
@locked
def toggle_wish():
    items = storage.read_json("wishes.json") or []
    for w in items:
        if w.get("id") == request.form.get("id"):
            w["hidden"] = not w.get("hidden")
            flash("Message hidden from the page." if w["hidden"] else "Message is visible again.",
                  "success")
            storage.write_json("wishes.json", items)
            break
    return redirect(url_for("admin") + "#wishes")


@app.route("/admin/delete-wish", methods=["POST"])
@login_required
@locked
def delete_wish():
    items = storage.read_json("wishes.json") or []
    items = [w for w in items if w.get("id") != request.form.get("id")]
    storage.write_json("wishes.json", items)
    flash("Message deleted.", "success")
    return redirect(url_for("admin") + "#wishes")


@app.errorhandler(413)
def file_too_large(e):
    flash("File too large — maximum is 25 MB per upload.", "error")
    target = url_for("admin") if session.get("logged_in") else url_for("index")
    return redirect(target)


storage.init()
_saved_stats = storage.read_json("stats.json")
if _saved_stats:
    _visit_stats.update(visits=_saved_stats.get("visits", 0),
                        guests=_saved_stats.get("guests", {}),
                        daily=_saved_stats.get("daily", {}))


def _reminder_loop():
    """Daily ~9:00 ICT Telegram digest: pending approvals, silent guests,
    days until the deadline/wedding. Only runs when Telegram is configured."""
    last_sent = None
    while True:
        time.sleep(1200)
        try:
            if not telegram_enabled():
                continue
            now = datetime.now(timezone(timedelta(hours=7)))
            if now.hour != 9 or last_sent == now.date():
                continue
            last_sent = now.date()
            c = load_content()
            rsvps = storage.read_json("rsvp.json") or []
            responded = {r.get("name", "").strip().casefold() for r in rsvps}
            silent = [g["name"] for g in c.get("guest_list", [])
                      if g["name"].casefold() not in responded]
            pending_photos = sum(1 for p in (storage.read_json("guest_photos.json") or [])
                                 if not p.get("approved"))
            pending_voices = sum(1 for v in (storage.read_json("voice_wishes.json") or [])
                                 if not v.get("approved"))
            lines = ["📋 Daily wedding digest"]
            try:
                days = (datetime.fromisoformat(c["date_iso"]) - now).days
                if days >= 0:
                    lines.append(f"💍 {days} day(s) until the wedding")
            except ValueError:
                pass
            if c.get("guest_list"):
                lines.append(f"⌛ {len(silent)} guest(s) have not RSVP'd")
            if pending_photos:
                lines.append(f"📷 {pending_photos} photo(s) waiting for approval")
            if pending_voices:
                lines.append(f"🎙 {pending_voices} voice blessing(s) waiting for approval")
            if len(lines) > 1:
                notify_telegram("\n".join(lines))
        except Exception as e:
            print(f"[reminder] Warning: {e}")


threading.Thread(target=_reminder_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7860, debug=True)
