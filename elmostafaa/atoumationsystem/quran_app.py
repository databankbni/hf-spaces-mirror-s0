from flask import Flask, request, jsonify
import subprocess, os, re, math, requests, uuid, time
import random, shutil
import arabic_reshaper
from bidi.algorithm import get_display

app = Flask(__name__)

AUDIO_DIR = "/audio"
VIDEO_DIR = "/videos"
IMAGE_DIR = "/images"
FONT_DIR  = "/fonts"

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")

# ─── HELPERS ────────────────────────────────────────────────────────────────

def get_audio_duration(path):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True
        )
        return float(r.stdout.strip() or "5")
    except:
        return 5.0

def download_file(url, dest, retries=3):
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            with open(dest, "wb") as f:
                f.write(r.content)
            return True
        except Exception as e:
            print(f"  Download attempt {attempt+1} failed: {e}")
            time.sleep(3)
    return False

def reshape_arabic(text):
    # نرجع النص زي ما هو بدون أي تعديل
    return text

def seconds_to_ass_time(seconds):
    h  = int(seconds // 3600)
    m  = int((seconds % 3600) // 60)
    s  = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def extract_pexels_video_id(url_or_id: str) -> str:
    """
    يقبل رابط بيكسيلز كامل زي:
    https://www.pexels.com/video/aerial-view-of-a-city-1234567/
    أو ID مباشر: 1234567
    """
    if url_or_id.isdigit():
        return url_or_id
    match = re.search(r"-(\d+)/?$", url_or_id.rstrip("/"))
    if match:
        return match.group(1)
    match = re.search(r"/video/[^/]*?(\d+)", url_or_id)
    if match:
        return match.group(1)
    raise ValueError("Could not extract video ID from the given URL")

def get_pexels_download_link(video_id: str, quality: str = "hd") -> str:
    """
    يستدعي Pexels API عشان يجيب رابط تحميل مباشر للفيديو.
    quality: 'hd', 'sd', أو 'uhd'
    """
    if not PEXELS_API_KEY:
        raise RuntimeError("PEXELS_API_KEY is not set in environment variables")

    api_url = f"https://api.pexels.com/videos/videos/{video_id}"
    headers = {"Authorization": PEXELS_API_KEY}
    resp = requests.get(api_url, headers=headers, timeout=30)

    if resp.status_code != 200:
        raise RuntimeError(f"Pexels API error {resp.status_code}: {resp.text}")

    data = resp.json()
    video_files = data.get("video_files", [])
    if not video_files:
        raise RuntimeError("No video files found for this Pexels video")

    matching = [f for f in video_files if f.get("quality") == quality]
    chosen = matching[0] if matching else video_files[0]
    return chosen["link"]

def get_video_duration(file_path: str) -> float:
    """يرجع مدة الفيديو بالثانية باستخدام ffprobe"""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    return float(result.stdout.strip())

def get_video_dimensions(file_path: str) -> tuple:
    """يرجع (width, height) للفيديو باستخدام ffprobe"""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=s=x:p=0",
        file_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    width, height = result.stdout.strip().split("x")
    return int(width), int(height)

# ─── ENDPOINT 1: DOWNLOAD & MERGE AUDIO ─────────────────────────────────────

@app.route("/api/download-audio", methods=["POST"])
def download_audio():
    try:
        data      = request.json
        ayah_urls = data.get("ayahUrls", [])
        ts        = data.get("ts", "") or str(uuid.uuid4().hex)[:8]

        if not ayah_urls:
            return jsonify({"error": "No ayahUrls provided"}), 400

        local_paths = []
        durations   = []

        # 1. تحميل الآيات المنفصلة وحساب مدتها
        for i, url in enumerate(ayah_urls):
            dest = os.path.join(AUDIO_DIR, f"{ts}_ayah_{i}.mp3")
            if download_file(url, dest):
                local_paths.append(dest)
                durations.append(get_audio_duration(dest))

        if not local_paths:
            return jsonify({"error": "Failed to download any audio files"}), 500

        # 2. إنشاء ملف التكست المخصص للدمج (Concat)
        concat_txt_path = os.path.join(AUDIO_DIR, f"{ts}_concat.txt")
        with open(concat_txt_path, "w", encoding="utf-8") as f:
            for path in local_paths:
                f.write(f"file '{path}'\n")

        # مسار ملف المطر اللي إنت حطيته في نفس الفولدر
        rain_bg_path = os.path.join(AUDIO_DIR, "rain_background.mp3")
        out_audio_path = os.path.join(AUDIO_DIR, f"{ts}_final.mp3")

        # 3. بناء أمر FFmpeg الاحترافي (السرعة + الحدة + الصدى + دمج المطر)
        if os.path.exists(rain_bg_path):
            # لو ملف المطر موجود، نطبق الخلطة السحرية الكاملة
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", concat_txt_path, # مدخل 0: صوت الشيخ
                "-i", rain_bg_path,                                 # مدخل 1: صوت المطر
                "-filter_complex", 
                (
                    # تعديل الشيخ: سرعة 1.01 + لعب في التردد عشان البصمة الرقمية + صدى صوت هادي
                    "[0:a]atempo=1.01,aresample=44100,asetrate=44100*1.003,atempo=0.997,aecho=0.8:0.3:40:0.2[sheikh_modified];"
                    # تعديل المطر: خفض الصوت جداً (0.04) عشان ميعليش على الشيخ + قصه على قد مدة الشيخ
                    f"[1:a]volume=0.04,atrim=0:duration={sum(durations)}[rain_trimmed];"
                    # دمج الاتنين في تراك واحد
                    "[sheikh_modified][rain_trimmed]amerge=inputs=2,pan=stereo|c0=c0+0.1*c2|c1=c1+0.1*c3,volume=2.5[audio_out]"
                ),
                "-map", "[audio_out]",
                "-c:a", "libmp3lame", "-b:a", "192k",
                out_audio_path
            ]
        else:
            # لو ملف المطر مش موجود لأي سبب، الكود مش هيعطل وهيشتغل بالفلاتر بس عشان الأمان
            print("⚠️ Warning: rain_background.mp3 not found! Running with filters only.")
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", concat_txt_path,
                "-filter_complex", "atempo=1.01,asetrate=44100*1.003,atempo=0.997,aecho=0.8:0.3:40:0.2,volume=2.0",
                "-c:a", "libmp3lame", "-b:a", "192k",
                out_audio_path
            ]

        # تشغيل الأمر على السيرفر
        subprocess.run(cmd, capture_output=True, text=True)

        # 4. تنظيف مساحة السيرفر فوراً ومسح الملفات المؤقتة
        try:
            os.remove(concat_txt_path)
            for p in local_paths:
                os.remove(p)
        except: pass

        # الحسبة الدقيقة للمدة بعد تسريع الصوت بنسبة 1%
        final_duration = sum(durations) / 1.01

        # الرد بنفس شكل الـ output القديم بالظبط عشان n8n ميعطلش
        total = final_duration
        hours = int(total // 3600)
        minutes = int((total % 3600) // 60)
        import math
        seconds = math.ceil(total % 60)
        duration_formatted = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        return jsonify({
            "audio_path":        out_audio_path,
            "ayah_durations":    durations,
            "total_duration":    final_duration,
            "duration_formatted": duration_formatted,
            "ts":                ts,
            "status":            "success"
        })

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ─── ENDPOINT 2: FETCH QURAN TEXT ────────────────────────────────────────────

def to_arabic_digits(num):
    """يحوّل رقم عادي (زي 5) لأرقام عربية (زي ٥)."""
    arabic_digits = "٠١٢٣٤٥٦٧٨٩"
    return "".join(arabic_digits[int(d)] for d in str(num))


# ─── ENDPOINT 2: FETCH QURAN TEXT ────────────────────────────────────────────
@app.route("/api/fetch-text", methods=["POST"])
def fetch_text():
    try:
        data       = request.json
        surah_id   = data.get("surahId", 2)
        start_ayah = data.get("startAyah", 1)
        end_ayah   = data.get("endAyah", 1)
        ayah_texts = []
        for ayah_num in range(start_ayah, end_ayah + 1):
            try:
                url  = f"https://api.quran.com/api/v4/quran/verses/uthmani?verse_key={surah_id}:{ayah_num}"
                r    = requests.get(url, timeout=15)
                d    = r.json()
                text = d["verses"][0]["text_uthmani"] if d.get("verses") else f"آية {ayah_num}"
            except:
                text = f"آية {ayah_num}"

            # إضافة رقم الآية بين نفس القوسين الزخرفيين المستخدمين مع السورة/الشيخ
            ayah_number_deco = f"\uFD3E{to_arabic_digits(ayah_num)}\uFD3F"
            text_with_number = f"{text} {ayah_number_deco}"

            ayah_texts.append(text_with_number)
        return jsonify({
            "ayah_texts": ayah_texts,
            "count":      len(ayah_texts),
            "status":     "success"
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500
        
# ─── ENDPOINT 3: FETCH PEXELS PHOTOS ─────────────────────────────────────────

@app.route("/api/fetch-media", methods=["POST"])
def fetch_media():
    try:
        data           = request.json
        background     = data.get("background", "nature")
        ayah_durations = data.get("ayah_durations", [])
        ts             = data.get("ts", str(uuid.uuid4())[:8])
        count          = len(ayah_durations)

        os.makedirs(IMAGE_DIR, exist_ok=True)
        headers = {"Authorization": PEXELS_API_KEY}

        # نجيب صور بجودة عالية من Pexels
        photo_urls = []
        page = 1
        while len(photo_urls) < count and page <= 5:
            try:
                r = requests.get(
                    "https://api.pexels.com/v1/search",
                    headers=headers,
                    params={"query": background, "per_page": 20,
                            "page": page, "orientation": "portrait"},
                    timeout=15
                )
                for photo in r.json().get("photos", []):
                    photo_urls.append(photo["src"]["original"])
                    if len(photo_urls) >= count:
                        break
                page += 1
            except Exception as e:
                print(f"  Pexels error page {page}: {e}")
                break

        if not photo_urls:
            return jsonify({"error": "No photos found from Pexels"}), 500

        print(f"  Found {len(photo_urls)} photos from Pexels")

        # نحمل صورة لكل آية
        media_paths = []
        for i in range(count):
            url  = photo_urls[i % len(photo_urls)]
            dest = f"{IMAGE_DIR}/{ts}_media_{i}.jpg"
            print(f"  Downloading photo {i+1}/{count}")
            if download_file(url, dest):
                media_paths.append(dest)
            time.sleep(0.2)

        if not media_paths:
            return jsonify({"error": "No media downloaded from Pexels"}), 500

        return jsonify({
            "media_paths": media_paths,
            "count":       len(media_paths),
            "ts":          ts,
            "status":      "success"
        })

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ─── ENDPOINT 3B: PREPARE VIDEO (فيديو حقيقي من Pexels بدل الصور) ────────────

@app.route("/api/prepare-video", methods=["POST"])
def prepare_video():
    """
    مسار بديل لـ fetch-media + normalize-media: بيجيب فيديو حقيقي
    من Pexels ويظبط مدته بالظبط على مدة الصوت (يقصه أو يكرره)
    مع تعديل بصري (فليب + تغميق سينمائي + فينييت) عشان يبقى مختلف
    عن النسخة الأصلية ومايبانش شكل ستوك.
    INPUT:  { video_url, audio_duration, quality, ts }
    OUTPUT: { file_path, video_duration_original, audio_duration, looped, width, height, ts }
    """
    try:
        data           = request.json
        video_url      = data.get("video_url", "")
        audio_duration = data.get("audio_duration")
        quality        = data.get("quality", "hd")
        ts             = data.get("ts", str(uuid.uuid4().hex)[:8])

        if not video_url:
            return jsonify({"error": "No video_url provided"}), 400
        if audio_duration is None:
            return jsonify({"error": "No audio_duration provided"}), 400

        audio_duration = float(audio_duration)
        os.makedirs(VIDEO_DIR, exist_ok=True)

        raw_path   = f"{VIDEO_DIR}/{ts}_raw.mp4"
        final_path = f"{VIDEO_DIR}/{ts}_prepared.mp4"

        # 1) رابط التحميل المباشر من Pexels
        video_id      = extract_pexels_video_id(video_url)
        download_link = get_pexels_download_link(video_id, quality)

        # 2) تنزيل الفيديو
        if not download_file(download_link, raw_path):
            return jsonify({"error": "Failed to download video from Pexels"}), 500

        # 3) مدة ومقاس الفيديو
        video_duration = get_video_duration(raw_path)
        video_width, video_height = get_video_dimensions(raw_path)

        # فلتر بصري: فليب أفقي + تغميق سينمائي (كونتراست أعلى + برايتنس سالب +
        # تشبع أقل + جاما أغمق) + curves داكنة + فينييت خفيف على الأطراف
        visual_filter = (
            "hflip,"
            "eq=contrast=1.15:brightness=-0.08:saturation=0.9:gamma=0.85,"
            "curves=preset=darker,"
            "vignette=PI/4"
        )

        # 4) نقص أو نكرر (loop) حسب مدة الصوت - مع تطبيق الفلتر في الحالتين
        if video_duration >= audio_duration:
            cmd = [
                "ffmpeg", "-y",
                "-i", raw_path,
                "-t", str(audio_duration),
                "-vf", visual_filter,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-c:a", "aac",
                final_path
            ]
        else:
            loops_needed = math.ceil(audio_duration / video_duration)
            cmd = [
                "ffmpeg", "-y",
                "-stream_loop", str(loops_needed - 1),
                "-i", raw_path,
                "-t", str(audio_duration),
                "-vf", visual_filter,
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-c:a", "aac",
                final_path
            ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            return jsonify({
                "error": "ffmpeg processing failed",
                "details": result.stderr
            }), 500

        try: os.remove(raw_path)
        except: pass

        import shutil
        os.makedirs("/home/appuser/.n8n-files", exist_ok=True)
        n8n_path = f"/home/appuser/.n8n-files/{ts}_prepared.mp4"
        shutil.copy(final_path, n8n_path)

        return jsonify({
            "file_path":               final_path,
            "video_duration_original": video_duration,
            "audio_duration":          audio_duration,
            "looped":                  video_duration < audio_duration,
            "width":                   video_width,
            "height":                  video_height,
            "ts":                      ts,
            "status":                  "success"
        })

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ─── ENDPOINT  PREPARE VIDEO v4  ─────────────────────────
import os
import shutil
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
from flask import request, jsonify
from PIL import Image, ImageDraw

CLIP_LEN_SEC     = 4.0     # مدة كل كليب ثابتة
CORNER_RADIUS    = 90      # نصف قطر الزوايا المدورة (بكسل)
CANVAS_W         = 1920    # عرض الكانفاس الخارجي الثابت
CANVAS_H         = 1080    # طول الكانفاس الخارجي الثابت
CONTENT_W        = 1920    # عرض كارت الفيديو الداخلي
CONTENT_H        = 1080    # طول كارت الفيديو الداخلي
TARGET_FPS       = 30      # فريم ريت موحد لكل الكليبات

# فلتر بصري نهائي — خفيف وطبيعي
FINAL_COLOR_FILTER = (
    "hflip,"
    "eq=contrast=1.05:brightness=-0.01:saturation=1.0:gamma=0.98"
)

def _run(cmd, timeout=300):
    """تشغيل أمر ffmpeg وإرجاع النتيجة، مع رفع استثناء لو فشل."""
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-4000:])
    return result

def _extract_clip(url, clip_len, out_path, target_w, target_h):
    """
    قص مباشر من الرابط (HTTP Range Request) باستخدام -ss قبل -i،
    بيبدأ من ثانية 0 لكل فيديو (أو تقدر تعدلها) بالمدة الثابتة (4 ثواني).
    """
    vf = (
        f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
        f"crop={target_w}:{target_h},"
        f"fps={TARGET_FPS}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-ss", "0",              # نقطة البداية من أول الفيديو مباشرة
        "-i", url,
        "-t", str(clip_len),
        "-vf", vf,
        "-an",
        "-vsync", "cfr",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "12",
        out_path,
    ]
    _run(cmd)

def _extract_clip(clip_item, out_path, target_w, target_h):
    """
    قص مباشر من الرابط مع التأكد من استخراج الـ URL كنص صريح
    """
    # استخراج الرابط وتجهيز البيانات بأمان تام لو كانت جايّة في شكل Dict أو نص
    if isinstance(clip_item, dict):
        url = clip_item.get("url")
        start_time = clip_item.get("start", 0.0)
        clip_duration = clip_item.get("len", CLIP_LEN_SEC)
    else:
        url = str(clip_item)
        start_time = 0.0
        clip_duration = CLIP_LEN_SEC

    vf = (
        f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
        f"crop={target_w}:{target_h},"
        f"fps={TARGET_FPS}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_time),
        "-i", url,
        "-t", str(clip_duration),
        "-vf", vf,
        "-an",
        "-vsync", "cfr",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "12",
        str(out_path),
    ]
    _run(cmd)

def _extract_all_clips(plan, work_dir, target_w, target_h, max_workers=3):
    """قص الكليبات بالتوازي بأمان تام"""
    clip_paths = [None] * len(plan)

    def _one(idx):
        out_p = f"{work_dir}/clip_{idx}.mp4"
        _extract_clip(plan[idx], out_p, target_w, target_h)
        return idx, out_p

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for idx, path in ex.map(_one, range(len(plan))):
            clip_paths[idx] = path

    return clip_paths

def _concat_simple(clip_paths, out_path):
    """دمج سريع بـ stream copy لأن الفريمات والمقاسات موحدة تماماً"""
    if len(clip_paths) == 1:
        shutil.copy(clip_paths[0], out_path)
        return

    list_file = out_path + "_list.txt"
    with open(list_file, "w") as f:
        for p in clip_paths:
            abs_p = os.path.abspath(p)
            f.write(f"file '{abs_p}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_file,
        "-c", "copy",
        out_path,
    ]
    _run(cmd)
    os.remove(list_file)

def _build_rounded_mask_png(w, h, radius, mask_path):
    """إنشاء قناع الحواف المدورة"""
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), (w - 1, h - 1)], radius=radius, fill=255)
    mask.save(mask_path)

def _finalize(concat_path, mask_path, audio_duration, canvas_w, canvas_h,
                content_w, content_h, out_path):
    """
    الخطوة النهائية: دمج الكارت المدور، الفلتر البصري، وقص الفيديو على مدة الصوت،
    بجودة عالية CRF 18 وضغط متوسط لضمان سرعة المعالجة وحجم تحت 50 ميجا للتيليجرام.
    """
    y_offset = (canvas_h - content_h) // 2
    x_offset = (canvas_w - content_w) // 2

    filter_complex = (
        f"[0:v]{FINAL_COLOR_FILTER}[colored];"
        f"[colored][1:v]alphamerge[rgba];"
        f"color=black:size={canvas_w}x{canvas_h}:d={audio_duration}[bg];"
        f"[bg][rgba]overlay={x_offset}:{y_offset}:shortest=1[outv]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", concat_path,
        "-loop", "1", "-i", mask_path,
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-t", str(audio_duration),
        "-c:v", "libx264",
        "-preset", "medium",  # توازن مثالي بين السرعة وضغط الحجم
        "-crf", "18",         # جودة عالية جداً ونقاء ممتاز
        "-pix_fmt", "yuv420p",
        out_path,
    ]
    _run(cmd)

@app.route("/api/prepare-video-v4", methods=["POST"])
def prepare_video_v4():
    """
    INPUT:  { video_urls: [..], audio_duration, ts }
    - يستقبل الروابط مباشرة كما هي ظاهرة من n8n
    - يقص 4 ثواني من كل فيديو مباشرة عبر HTTP Range (بدون تحميل كامل)
    - جودة عالية CRF 18 ومساحة ملف آمنة تماماً للتيليجرام
    """
    try:
        data = request.json
        clips_in = data.get("clips", [])
        audio_duration = data.get("audio_duration")
        ts = data.get("ts", str(uuid.uuid4().hex)[:8])

        if not clips_in or len(clips_in) < 2:
            return jsonify({"error": "Need at least 2 clips in clips array"}), 400
        if audio_duration is None:
            return jsonify({"error": "No audio_duration provided"}), 400

        audio_duration = float(audio_duration)
        os.makedirs(VIDEO_DIR, exist_ok=True)
        work_dir = f"{VIDEO_DIR}/{ts}_work"
        os.makedirs(work_dir, exist_ok=True)

        canvas_w, canvas_h = CANVAS_W, CANVAS_H
        content_w, content_h = CONTENT_W, CONTENT_H
# خطة الكليبات باستخدام الـ clips المجهزة (url + duration)
        plan = _build_clip_plan(clips_in, audio_duration)
        # قص الكليبات بالتوازي (كل فيديو بناخد منه 4 ثواني مباشرة من الرابط)
        clip_paths = _extract_all_clips(plan, work_dir, content_w, content_h, max_workers=3)

        if any(p is None for p in clip_paths):
            return jsonify({"error": "Failed to extract one or more clips"}), 500

        # دمج الكليبات
        concat_path = f"{work_dir}/concat.mp4"
        _concat_simple(clip_paths, concat_path)

        # إنشاء قناع الحواف المدورة
        mask_path = f"{work_dir}/mask.png"
        _build_rounded_mask_png(content_w, content_h, CORNER_RADIUS, mask_path)

        # التنسيق والإخراج النهائي
        final_path = f"{VIDEO_DIR}/{ts}_prepared.mp4"
        _finalize(concat_path, mask_path, audio_duration, canvas_w, canvas_h,
                  content_w, content_h, final_path)

        width, height = get_video_dimensions(final_path)

        # تنظيف الملفات المؤقتة
        shutil.rmtree(work_dir, ignore_errors=True)

        # نسخ الملف إلى مسار n8n
        os.makedirs("/home/appuser/.n8n-files", exist_ok=True)
        n8n_path = f"/home/appuser/.n8n-files/{ts}_prepared.mp4"
        shutil.copy(final_path, n8n_path)

        return jsonify({
            "file_path": final_path,
            "num_sources": len(video_urls),
            "num_segments": len(video_urls),
            "audio_duration": audio_duration,
            "width": width,
            "height": height,
            "ts": ts,
            "status": "success"
        })

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500
        
# ─── ENDPOINT 3C: PREPARE VIDEO v3 (نسخة مصححة) ─────────────────────────
# الإصلاحات في النسخة دي:
#   1) مقاس كانفاس ثابت 1080x1920 (عمودي/ريلز) بدل "أصغر فيديو مصدر"
#   2) scale (cover) قبل crop بدل crop مباشر → مفيش زوم كارثي، المنظر الواسع بيفضل واسع
#   3) هامش أمان عند اختيار نقطة البداية لكل كليب → مفيش فريمات ثابتة/كليبات مبتورة
#   4) فرض فريم ريت موحد (30fps) على كل الكليبات → دمج concat يبقى سليم 100%
#   5) تحميل الفيديوهات بالتوازي + قص الكليبات بالتوازي → سرعة أعلى بكتير
#   6) دمج بـ stream copy (-c copy) بدل إعادة ترميز → دمج فوري تقريبًا
#   7) تخفيف الفلاتر النهائية (vignette + film grain) → جودة بصرية أنضف

import os
import math
import shutil
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor

from PIL import Image, ImageDraw

CLIP_LEN_SEC     = 4.0     # مدة كل كليب ثابتة
CORNER_RADIUS    = 90      # نصف قطر الزوايا المدورة (بكسل) — أكبر عشان تبان واضحة
CANVAS_W         = 1920    # مقاس الكانفاس الخارجي الثابت (عرض) — أفقي/landscape
CANVAS_H         = 1080    # مقاس الكانفاس الخارجي الثابت (طول)
CONTENT_W        = 1920    # عرض كارت الفيديو = عرض الكانفاس بالكامل (مفيش letterbox)
CONTENT_H         = 1080    # طول كارت الفيديو = طول الكانفاس بالكامل (يملا الشاشة)
TARGET_FPS       = 30      # فريم ريت موحد لكل الكليبات (ضروري لسلامة الدمج بـ copy)
SAFETY_MARGIN    = 0.35    # هامش أمان (ثانية) لتجنب القص قرب نهاية الفيديو المصدر

# فلتر بصري نهائي — خفيف وطبيعي (تباين بسيط + فينيت خفيف)، من غير تلوين قوي
FINAL_COLOR_FILTER = (
    "hflip,"
    "eq=contrast=1.05:brightness=-0.01:saturation=1.0:gamma=0.98"
)


def _run(cmd, timeout=300):
    """تشغيل أمر ffmpeg وإرجاع النتيجة، مع رفع استثناء لو فشل."""
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-4000:])
    return result


def _build_clip_plan(video_paths, target_total):
    """
    round-robin بالدورات: كل دورة = كليب واحد من كل فيديو، بالترتيب.
    بيراعي هامش أمان (SAFETY_MARGIN) عشان مايقصش قريب جدًا من نهاية الفيديو
    (ده اللي كان بيسبب كليبات بتتحول لفريم ثابت/صورة).
    فيديوهات مدتها أقل من كليب واحد + هامش الأمان بيتم تجاهلها من الخطة.
    """
    durations = [get_video_duration(p) for p in video_paths]

    # نستبعد أي فيديو مصدر قصير جدًا (أقل من كليب واحد + هامش أمان)
    usable = [
        (p, d) for p, d in zip(video_paths, durations)
        if d >= (CLIP_LEN_SEC + SAFETY_MARGIN)
    ]
    if not usable:
        raise RuntimeError("كل الفيديوهات المصدر قصيرة جدًا عن مدة كليب واحد")

    paths_u = [u[0] for u in usable]
    durs_u  = [u[1] for u in usable]

    n_sources = len(paths_u)
    total_clips_needed = math.ceil(target_total / CLIP_LEN_SEC)
    n_cycles = math.ceil(total_clips_needed / n_sources)

    cursors = [0.0 for _ in paths_u]

    plan = []
    for _cycle in range(n_cycles):
        for src_idx in range(n_sources):
            src = paths_u[src_idx]
            dur = durs_u[src_idx]
            start = cursors[src_idx]

            usable_end = dur - SAFETY_MARGIN
            # لو المؤشر وصل قريب من نهاية الفيديو (مع هامش الأمان)، نرجع نلف من الأول
            if start + CLIP_LEN_SEC > usable_end:
                start = 0.0

            plan.append({"path": src, "start": start, "len": CLIP_LEN_SEC})
            cursors[src_idx] = start + CLIP_LEN_SEC

    return plan


def _extract_clip(clip, out_path, target_w, target_h):
    """
    scale+crop لتوحيد نسبة الفيديو على CONTENT_W×CONTENT_H (قريبة من 16:9
    الأصلية لمعظم فيديوهات Pexels)، فالقص بيكون خفيف جدًا (طبيعي) بدل قص
    كامل الطول — المنظر الواسع بيفضل واسع تقريبًا زي الأصل.
    فريم ريت موحد (TARGET_FPS) عشان الدمج بـ stream copy يبقى سليم.
    """
    vf = (
        f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
        f"crop={target_w}:{target_h},"
        f"fps={TARGET_FPS}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(clip["start"]),
        "-i", clip["path"],
        "-t", str(clip["len"]),
        "-vf", vf,
        "-an",
        "-vsync", "cfr",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "12",
        out_path,
    ]
    _run(cmd)


def _extract_all_clips(plan, work_dir, target_w, target_h, max_workers=3):
    """قص كل الكليبات بالتوازي (max_workers محدود عشان الموارد المشتركة)."""
    clip_paths = [None] * len(plan)

    def _one(idx):
        out_p = f"{work_dir}/clip_{idx}.mp4"
        _extract_clip(plan[idx], out_p, target_w, target_h)
        return idx, out_p

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for idx, path in ex.map(_one, range(len(plan))):
            clip_paths[idx] = path

    return clip_paths


def _concat_simple(clip_paths, out_path):
    """
    دمج باستخدام concat demuxer + stream copy (بدون إعادة ترميز).
    بما إن كل الكليبات دلوقتي بنفس المقاس ونفس الفريم ريت (بعد التعديل)،
    الدمج بيبقى سليم 100% بدون أي فريمات مبعوجة أو تجميد.
    """
    if len(clip_paths) == 1:
        shutil.copy(clip_paths[0], out_path)
        return

    list_file = out_path + "_list.txt"
    with open(list_file, "w") as f:
        for p in clip_paths:
            abs_p = os.path.abspath(p)
            f.write(f"file '{abs_p}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_file,
        "-c", "copy",
        out_path,
    ]
    _run(cmd)
    os.remove(list_file)


def _build_rounded_mask_png(w, h, radius, mask_path):
    """قناع PNG (أبيض بزوايا مدورة شفافة)، بيتحسب مرة واحدة بس."""
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), (w - 1, h - 1)], radius=radius, fill=255)
    mask.save(mask_path)


def _finalize(concat_path, mask_path, audio_duration, canvas_w, canvas_h,
               content_w, content_h, out_path):
    """
    خطوة نهائية واحدة: فلاتر بصرية (مخففة) + حواف مدورة على الفيديو نفسه
    (الكارت) + توسيطه فوق كانفاس أسود أكبر (letterbox) + قص على مدة الصوت.
    ده اللي بيدي شكل الحواف السودة فوق وتحت + الكارت المدور الحواف.
    """
    y_offset = (canvas_h - content_h) // 2
    x_offset = (canvas_w - content_w) // 2

    filter_complex = (
        f"[0:v]{FINAL_COLOR_FILTER}[colored];"
        f"[colored][1:v]alphamerge[rgba];"
        f"color=black:size={canvas_w}x{canvas_h}:d={audio_duration}[bg];"
        f"[bg][rgba]overlay={x_offset}:{y_offset}:shortest=1[outv]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", concat_path,
        "-loop", "1", "-i", mask_path,
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-t", str(audio_duration),
        "-c:v", "libx264", "-preset", "medium", "-crf", "16",
        out_path,
    ]
    _run(cmd)


@app.route("/api/prepare-video-v3", methods=["POST"])
def prepare_video_v3():
    """
    INPUT:  { video_urls: [..], audio_duration, quality, ts }
    OUTPUT: { file_path, num_sources, num_segments, audio_duration,
              width, height, ts, status }
    """
    try:
        data = request.json
        video_urls = data.get("video_urls", [])
        audio_duration = data.get("audio_duration")
        quality = data.get("quality", "hd")
        ts = data.get("ts", str(uuid.uuid4().hex)[:8])

        if not video_urls or len(video_urls) < 2:
            return jsonify({"error": "Need at least 2 video_urls"}), 400
        if audio_duration is None:
            return jsonify({"error": "No audio_duration provided"}), 400

        audio_duration = float(audio_duration)
        os.makedirs(VIDEO_DIR, exist_ok=True)
        work_dir = f"{VIDEO_DIR}/{ts}_work"
        os.makedirs(work_dir, exist_ok=True)

        # 1) تحميل كل الفيديوهات المصدر (بالتوازي)
        def _download_one(args):
            i, url = args
            video_id = extract_pexels_video_id(url)
            download_link = get_pexels_download_link(video_id, quality)
            raw_path = f"{work_dir}/src_{i}.mp4"
            ok = download_file(download_link, raw_path)
            return raw_path if ok else None

        with ThreadPoolExecutor(max_workers=len(video_urls)) as ex:
            raw_paths = list(ex.map(_download_one, enumerate(video_urls)))

        if any(p is None for p in raw_paths):
            return jsonify({"error": "Failed to download one or more videos"}), 500

        # 2) مقاسات ثابتة: الكانفاس الخارجي (عمودي/ريلز) + كارت الفيديو الداخلي
        canvas_w, canvas_h = CANVAS_W, CANVAS_H
        content_w, content_h = CONTENT_W, CONTENT_H

        # 3) خطة الكليبات (round-robin + هامش أمان لتجنب الفريمات الثابتة)
        plan = _build_clip_plan(raw_paths, audio_duration)

        # 4) قص كل كليب على مقاس الكارت (content) لا الكانفاس الكامل
        clip_paths = _extract_all_clips(plan, work_dir, content_w, content_h, max_workers=3)

        # 5) دمج بـ stream copy (سريع وسليم)
        concat_path = f"{work_dir}/concat.mp4"
        _concat_simple(clip_paths, concat_path)

        # 6) قناع الحواف المدورة بمقاس الكارت (مش الكانفاس الكامل)
        mask_path = f"{work_dir}/mask.png"
        _build_rounded_mask_png(content_w, content_h, CORNER_RADIUS, mask_path)

        # 7) الخطوة النهائية: الكارت (مقصوص+مدور) فوق كانفاس أسود letterbox
        final_path = f"{VIDEO_DIR}/{ts}_prepared.mp4"
        _finalize(concat_path, mask_path, audio_duration, canvas_w, canvas_h,
                  content_w, content_h, final_path)

        width, height = get_video_dimensions(final_path)

        # 8) تنظيف الملفات المؤقتة
        shutil.rmtree(work_dir, ignore_errors=True)

        # 9) نسخة لمكان يوصله n8n
        os.makedirs("/home/appuser/.n8n-files", exist_ok=True)
        n8n_path = f"/home/appuser/.n8n-files/{ts}_prepared.mp4"
        shutil.copy(final_path, n8n_path)

        return jsonify({
            "file_path":     final_path,
            "num_sources":   len(raw_paths),
            "num_segments":  len(plan),
            "audio_duration": audio_duration,
            "width":  width,
            "height": height,
            "ts": ts,
            "status": "success"
        })

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500
        
# ─── ENDPOINT 4: NORMALIZE MEDIA (صورة → فيديو بـ Ken Burns) ─────────────────

@app.route("/api/normalize-media", methods=["POST"])
def normalize_media():
    """
    يحول كل صورة لفيديو بمدة الآية + Ken Burns
    صورة صورة عشان الجهاز ميهنجش
    INPUT:  { media_paths, ayah_durations, ts, width, height, suffix }
    OUTPUT: { clip_paths, ts, suffix }
    """
    try:
        data           = request.json
        media_paths    = data.get("media_paths", [])
        ayah_durations = data.get("ayah_durations", [])
        ts             = data.get("ts", str(uuid.uuid4())[:8])
        w              = int(data.get("width",  1080))
        h              = int(data.get("height", 1350))
        suffix         = data.get("suffix", "reels")

        if not media_paths or not ayah_durations:
            return jsonify({"error": "Missing media_paths or ayah_durations"}), 400

        os.makedirs(IMAGE_DIR, exist_ok=True)

        media_count = len(media_paths)
        clip_paths  = []

        # Ken Burns directions بالتناوب
        kb_effects = [
            "zoompan=z='min(zoom+0.0008,1.3)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
            "zoompan=z='if(lte(zoom,1.0),1.3,max(1.0,zoom-0.0008))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
            "zoompan=z='min(zoom+0.0008,1.3)':x='0':y='0'",
            "zoompan=z='min(zoom+0.0008,1.3)':x='iw-iw/zoom':y='ih-ih/zoom'",
        ]

        print(f"\n=== Normalizing {suffix} ({w}x{h}) ===")

        for i, duration in enumerate(ayah_durations):
            media_src = media_paths[i % media_count]
            out       = f"{IMAGE_DIR}/{ts}_{suffix}_clip_{i}.mp4"
            kb        = kb_effects[i % len(kb_effects)]
            fps       = 25
            nb_frames = int(duration * fps)

            print(f"  Clip {i+1}/{len(ayah_durations)} - {duration:.1f}s")

            vf = (
                f"scale={w*2}:{h*2}:force_original_aspect_ratio=increase,"
                f"crop={w*2}:{h*2},"
                f"{kb}:d={nb_frames}:s={w}x{h}:fps={fps},"
                f"setsar=1"
            )

            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", media_src,
                "-vf", vf,
                "-t", str(duration),
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-pix_fmt", "yuv420p",
                "-an",
                out
            ]

            result = subprocess.run(cmd, capture_output=True)
            if result.returncode == 0:
                clip_paths.append(out)
                print(f"  Clip {i+1} done ✓")
            else:
                print(f"  Clip {i+1} failed: {result.stderr.decode()[-300:]}")

        if not clip_paths:
            return jsonify({"error": "No clips generated"}), 500

        return jsonify({
            "clip_paths": clip_paths,
            "ts":         ts,
            "suffix":     suffix,
            "status":     "success"
        })

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ─── ENDPOINT 5: CONCAT SILENT ───────────────────────────────────────────────

@app.route("/api/concat-silent", methods=["POST"])
def concat_silent():
    """
    يدمج الكليبات في فيديو صامت
    INPUT:  { clip_paths, ts, suffix }
    OUTPUT: { silent_path, ts, suffix }
    """
    try:
        data       = request.json
        clip_paths = data.get("clip_paths", [])
        ts         = data.get("ts", str(uuid.uuid4())[:8])
        suffix     = data.get("suffix", "reels")

        if not clip_paths:
            return jsonify({"error": "No clip_paths provided"}), 400

        os.makedirs(VIDEO_DIR, exist_ok=True)

        silent = f"{VIDEO_DIR}/{ts}_{suffix}_silent.mp4"

        if len(clip_paths) == 1:
            subprocess.run(["cp", clip_paths[0], silent])
        else:
            list_file = f"{VIDEO_DIR}/{ts}_{suffix}_concat.txt"
            with open(list_file, "w") as f:
                for p in clip_paths:
                    f.write(f"file '{p}'\n")

            cmd = ["ffmpeg", "-y",
                   "-f", "concat", "-safe", "0",
                   "-i", list_file,
                   "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                   "-pix_fmt", "yuv420p",
                   silent]
            result = subprocess.run(cmd, capture_output=True)

            try: os.remove(list_file)
            except: pass

            if result.returncode != 0:
                return jsonify({"error": "Concat failed",
                                "stderr": result.stderr.decode()}), 500

        for p in clip_paths:
            try: os.remove(p)
            except: pass

        print(f"  Silent video → {silent}")
        return jsonify({
            "silent_path": silent,
            "ts":          ts,
            "suffix":      suffix,
            "status":      "success"
        })

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ─── إعدادات الخطوط والألوان (حط دي فوق الملف مرة واحدة، جنب الـ imports) ───
import re

FONT_AYAH   = "TE HAFS2 Tharwat Emara"   # الخط المصحفي التقليدي (كان DigitalKhatt New Madina)
FONT_HEADER = "TE HAFS2 Tharwat Emara"

WHITE = "&H00FFFFFF"
BLACK = "&H00000000"
RED   = "&H000000FF"

# علامات التشكيل العربي - بتتحسب كحروف منفصلة في len() بس مالهاش عرض فعلي عالشاشة
ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u08D4-\u08E1\u08E3-\u08FF]")


def visual_length(text: str) -> int:
    """طول النص "الفعلي" على الشاشة - بيتجاهل علامات التشكيل عشان متأثرش على قرار التقسيم/الحجم."""
    return len(ARABIC_DIACRITICS.sub("", text))


def decorate(text: str) -> str:
    """نص أبيض جوه قوسين حمر ﴾ ... ﴿"""
    return f"{{\\c{RED}}}\uFD3E{{\\c{WHITE}}}{text}{{\\c{RED}}}\uFD3F"


def wrap_ayah_text(text: str, threshold: int = 40):
    """يقسم نص الآية على سطرين لو طويل فعليًا (بيتجاهل التشكيل في حساب الطول)."""
    text = text.strip()
    if visual_length(text) <= threshold:
        return text, [text]

    words = text.split()
    if len(words) <= 1:
        return text, [text]

    total_vlen = visual_length(text)
    mid = total_vlen / 2
    best_split, best_diff, acc = 0, float("inf"), 0
    for i in range(len(words) - 1):
        acc += visual_length(words[i]) + 1
        diff = abs(acc - mid)
        if diff < best_diff:
            best_diff = diff
            best_split = i + 1

    line1 = " ".join(words[:best_split])
    line2 = " ".join(words[best_split:])
    return f"{line1}\\N{line2}", [line1, line2]


def ayah_font_size(lines, w, margin_lr, base_size):
    """يحسب حجم خط الآية حسب أطول سطر (طول فعلي من غير تشكيل)، نسبي لعرض الفيديو الحقيقي."""
    max_width = w - margin_lr * 2
    longest = max((visual_length(l) for l in lines), default=1) or 1
    fs = int(max_width / (longest * 0.55))
    return max(int(base_size * 0.45), min(base_size, fs))


# ─── ENDPOINT 6: CREATE ASS ──────────────────────────────────────────────────

@app.route("/api/create-ass", methods=["POST"])
def create_ass():
    try:
        data           = request.json
        ayah_texts     = data.get("ayah_texts", [])
        ayah_durations = data.get("ayah_durations", [])
        sheikh         = data.get("sheikh", "")
        ts             = data.get("ts", str(uuid.uuid4())[:8])
        w              = int(data.get("width",  1498))
        h              = int(data.get("height", 1080))

        if not ayah_texts or not ayah_durations:
            return jsonify({"error": "Missing ayah_texts or ayah_durations"}), 400

        os.makedirs(VIDEO_DIR, exist_ok=True)
        total_duration = sum(ayah_durations)

        # ── كل المقاسات والهوامش نسبية لأبعاد الفيديو الحقيقية (w, h) ──
        side_margin      = int(w * 0.03)
        bottom_margin    = int(h * 0.05)
        base_font_ayah   = int(h * 0.095)
        font_size_sheikh = int(h * 0.07)
        outline_ayah     = max(3, int(base_font_ayah * 0.015))
        outline_sheikh   = max(1, int(font_size_sheikh * 0.05))

        ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Ayah,{FONT_AYAH},{base_font_ayah},{WHITE},{WHITE},{BLACK},{BLACK},0,0,0,0,100,100,0,0,1,{outline_ayah},0,5,{side_margin},{side_margin},0,1
Style: Sheikh,{FONT_HEADER},{font_size_sheikh},{WHITE},{WHITE},{BLACK},{BLACK},0,1,0,0,100,100,0,0,1,{outline_sheikh},0,2,{side_margin},{side_margin},{bottom_margin},1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        end_time = seconds_to_ass_time(total_duration)

        # اسم الشيخ بس - تحت الشاشة، من غير قوسين حمر، ثابت طول الفيديو
        ass_content += (
            f"Dialogue: 0,0:00:00.00,{end_time},Sheikh,,0,0,0,,"
            f"الشَّيْخُ {sheikh}\n"
        )

        # الآيات في نص الشاشة تمامًا - حجم وتقسيم أسطر ديناميكي لكل آية
        current_time = 0.0
        for text, duration in zip(ayah_texts, ayah_durations):
            start = seconds_to_ass_time(current_time)
            end   = seconds_to_ass_time(current_time + duration)

            wrapped_text, lines = wrap_ayah_text(text)
            fs   = ayah_font_size(lines, w, side_margin, base_font_ayah)
            bord = max(3, int(fs * 0.03))

            override = f"\\fs{fs}\\bord{bord}"
            ass_content += f"Dialogue: 0,{start},{end},Ayah,,0,0,0,,{{{override}}}{wrapped_text}\n"
            current_time += duration

        ass_path = f"{VIDEO_DIR}/{ts}.ass"
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(ass_content)

        return jsonify({
            "ass_path": ass_path,
            "ts":       ts,
            "status":   "success"
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500
        
# ─── ENDPOINT 7: CREATE ASS (WORDS/GROUPS SYSTEM) ────────────────────────────
# حط الكود ده تحت endpoint create_ass القديم في نفس الملف بالظبط.
# بيستخدم نفس المتغيرات المعرّفة عندك فعلاً: app, VIDEO_DIR, seconds_to_ass_time,
# visual_length, os, uuid, re — مفيش أي import إضافي أو ملف تاني مطلوب.

import random

FONT_WORDS = "TE HAFS2 Tharwat Emara"   # نفس خط الآية، غيّره لو عايز

WHITE_W = "&H00FFFFFF"
BLACK_W = "&H00000000"


def _rgb_to_ass(r, g, b) -> str:
    return f"&H00{b:02X}{g:02X}{r:02X}"


# ألوان هادية مناسبة لأجواء القرآن - عدّل/زوّد زي ما تحب
COLOR_PALETTE = [
    _rgb_to_ass(255, 255, 255),  # أبيض
    _rgb_to_ass(255, 209, 102),  # دهبي فاتح
    _rgb_to_ass(129, 199, 195),  # فيروزي هادي
    _rgb_to_ass(230, 214, 181),  # بيج دافئ
    _rgb_to_ass(196, 181, 226),  # لافندر هادي
]

_color_bag = []


def _next_color():
    """لون عشوائي من غير تكرار لحد ما كل الألوان تتستخدم مرة."""
    global _color_bag
    if not _color_bag:
        _color_bag = COLOR_PALETTE.copy()
        random.shuffle(_color_bag)
    return _color_bag.pop()


def _dynamic_font_size(lines, w, margin_lr, base_size):
    max_width = w - margin_lr * 2
    longest = max((visual_length(l) for l in lines), default=1) or 1
    fs = int(max_width / (longest * 0.55))
    return max(int(base_size * 0.45), min(base_size, fs))


def _build_single_word(text, start, end, w, base_font):
    """كلمة منفردة: كبيرة في نص الشاشة، لون من الباليت، مع توهج (glow) وحركة pop-in."""
    fs = _dynamic_font_size([text], w, int(w * 0.05), base_font)
    color = _next_color()
    s = seconds_to_ass_time(start)
    e = seconds_to_ass_time(end)

    glow = (
        f"{{\\an5\\fs{fs}\\c{color}\\bord14\\blur25\\shad0\\1a&H40&"
        f"\\fscx70\\fscy70\\t(0,180,\\fscx105\\fscy105)}}"
    )
    sharp = (
        f"{{\\an5\\fs{fs}\\c{color}\\bord3\\blur2\\shad0"
        f"\\fscx70\\fscy70\\alpha&HFF&\\t(0,180,\\fscx100\\fscy100\\alpha&H00&)}}"
    )
    return (
        f"Dialogue: 0,{s},{e},Single,,0,0,0,,{glow}{text}\n"
        f"Dialogue: 1,{s},{e},Single,,0,0,0,,{sharp}{text}\n"
    )


def _build_group(text, start, end, w, base_font, reveal_ratio=0.65, min_hold=0.15):
    """مجموعة كلمات: تحت في التلت السفلي، بتتكتب تدريجيًا وتخلص قبل نهاية التوقيت."""
    words = text.split()
    n = len(words)
    duration = max(end - start, 0.05)
    reveal_duration = max(min(duration * reveal_ratio, duration - min_hold), 0.05)
    step = reveal_duration / n

    out = ""
    for i in range(1, n + 1):
        w_start = start + (i - 1) * step
        w_end = start + i * step if i < n else end
        partial = " ".join(words[:i])
        fs = _dynamic_font_size([partial], w, int(w * 0.04), base_font)
        s = seconds_to_ass_time(w_start)
        e = seconds_to_ass_time(w_end)
        tag = f"{{\\an2\\fs{fs}\\c{WHITE_W}\\bord4\\blur6\\shad0}}"
        out += f"Dialogue: 0,{s},{e},Group,,0,0,0,,{tag}{partial}\n"
    return out


@app.route("/api/create-ass-words", methods=["POST"])
def create_ass_words():
    """
    البيانات المطلوبة (JSON):
    {
      "entries": [
        {"text": "رَبِّ أَوْزِعْنِي أَنْ", "start": 3.80, "end": 4.75},
        {"text": "رَبِّ", "start": 22.00, "end": 22.80}
      ],
      "width": 1920, "height": 1080, "ts": "اختياري"
    }
    (لو النص في entry فيه كلمة واحدة -> بيتعامل كـ"كلمة منفردة"،
     لو فيه أكتر من كلمة -> بيتعامل كـ"مجموعة" بنظام التايب رايتر)
    """
    try:
        data = request.json
        entries = data.get("entries", [])
        w = int(data.get("width", 1920))
        h = int(data.get("height", 1080))
        ts = data.get("ts", str(uuid.uuid4())[:8])
        seed = data.get("seed")

        if not entries:
            return jsonify({"error": "Missing entries"}), 400

        if seed is not None:
            random.seed(seed)

        base_font_single = int(h * 0.16)
        base_font_group = int(h * 0.075)
        side_margin = int(w * 0.03)
        bottom_margin = int(h * 0.08)

        os.makedirs(VIDEO_DIR, exist_ok=True)

        ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Single,{FONT_WORDS},{base_font_single},{WHITE_W},{WHITE_W},{BLACK_W},{BLACK_W},1,0,0,0,100,100,0,0,1,3,0,5,{side_margin},{side_margin},0,1
Style: Group,{FONT_WORDS},{base_font_group},{WHITE_W},{WHITE_W},{BLACK_W},{BLACK_W},1,0,0,0,100,100,0,0,1,4,0,2,{side_margin},{side_margin},{bottom_margin},1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        for entry in entries:
            text = entry.get("text", "").strip()
            if not text:
                continue
            start = float(entry["start"])
            end = float(entry["end"])

            if len(text.split()) == 1:
                ass_content += _build_single_word(text, start, end, w, base_font_single)
            else:
                ass_content += _build_group(text, start, end, w, base_font_group)

        ass_path = f"{VIDEO_DIR}/{ts}_words.ass"
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(ass_content)

        return jsonify({
            "ass_path": ass_path,
            "ts": ts,
            "status": "success"
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500
        
# ─── ENDPOINT 7: RENDER FINAL ────────────────────────────────────────────────

@app.route("/api/render-final", methods=["POST"])
def render_final():
    """
    يدمج الفيديو الصامت + الصوت + ملف ASS
    INPUT:  { silent_path, audio_path, ass_path, ts, suffix }
    OUTPUT: { video_path, ts, suffix }
    """
    try:
        data        = request.json
        silent_path = data.get("silent_path")
        audio_path  = data.get("audio_path")
        ass_path    = data.get("ass_path")
        ts          = data.get("ts", str(uuid.uuid4())[:8])
        suffix      = data.get("suffix", "reels")

        if not silent_path or not os.path.exists(silent_path):
            return jsonify({"error": f"Silent video not found: {silent_path}"}), 400
        if not audio_path or not os.path.exists(audio_path):
            return jsonify({"error": f"Audio not found: {audio_path}"}), 400

        final    = f"{VIDEO_DIR}/{ts}_{suffix}.mp4"
        safe_ass = ass_path.replace("\\", "/").replace(":", "\\:") if ass_path else None

        cmd = [
            "ffmpeg", "-y",
            "-i", silent_path,
            "-i", audio_path,
            "-map", "0:v:0",
            "-map", "1:a:0",
            *(["-vf", f"ass='{safe_ass}':fontsdir=/fonts"] if ass_path and os.path.exists(ass_path) else []),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            "-pix_fmt", "yuv420p",
            final
        ]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            return jsonify({"error": "Render failed",
                            "stderr": result.stderr.decode()}), 500

        try: os.remove(silent_path)
        except: pass

        print(f"  Final video → {final}")
        import shutil
        os.makedirs("/home/appuser/.n8n-files", exist_ok=True)
        shutil.copy(final, f"/home/appuser/.n8n-files/{ts}_{suffix}.mp4")
        return jsonify({
            "video_path": final,
            "suffix":     suffix,
            "ts":         ts,
            "status":     "success"
        })

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ─── ENDPOINT 8: CLEANUP ─────────────────────────────────────────────────────

@app.route("/api/cleanup", methods=["POST"])
def cleanup():
    try:
        data        = request.json
        media_paths = data.get("media_paths", [])
        audio_path  = data.get("audio_path", "")
        ass_path    = data.get("ass_path", "")
        removed     = []
        for p in media_paths + [audio_path, ass_path]:
            try:
                if p and os.path.exists(p):
                    os.remove(p)
                    removed.append(p)
            except: pass
        return jsonify({"removed": removed, "status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
        
# ─── ENDPOINT: YT-DLP DOWNLOAD ───────────────────────────────────────────────

@app.route("/api/download-video", methods=["POST"])
def download_video():
    try:
        data     = request.json
        url      = data.get("url", "")
        quality  = data.get("quality", "best")
        fmt      = data.get("format", "mp4")
        start    = data.get("start", "")
        end      = data.get("end", "")
        ts       = data.get("ts", str(uuid.uuid4().hex)[:8])

        if not url:
            return jsonify({"error": "No URL provided"}), 400

        os.makedirs("/videos", exist_ok=True)
        out_path = f"/videos/{ts}_downloaded.%(ext)s"

        # بناء الأمر
        cmd = ["yt-dlp", "-o", out_path]

        # الجودة
        if quality == "audio":
            cmd += ["-x", "--audio-format", "mp3"]
        elif quality == "1080p":
            cmd += ["-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]"]
        elif quality == "720p":
            cmd += ["-f", "bestvideo[height<=720]+bestaudio/best[height<=720]"]
        elif quality == "480p":
            cmd += ["-f", "bestvideo[height<=480]+bestaudio/best[height<=480]"]
        elif quality == "360p":
            cmd += ["-f", "bestvideo[height<=360]+bestaudio/best[height<=360]"]
        else:
            cmd += ["-f", "best"]

        # تحميل جزء معين
        if start and end:
            cmd += ["--download-sections", f"*{start}-{end}"]
            
            cmd += ["--cookies", "/app/www.youtube.com_cookies.txt"]
            cmd += ["--impersonate", "chrome"]
            cmd.append(url)

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            return jsonify({
                "error": "Download failed",
                "details": result.stderr
            }), 500

        # نلاقي الملف اللي اتحمل
        import glob
        files = glob.glob(f"/videos/{ts}_downloaded.*")
        if not files:
            return jsonify({"error": "File not found after download"}), 500

        final_path = files[0]

        # نحطه في n8n-files عشان تقدر تاخده
        os.makedirs("/home/appuser/.n8n-files", exist_ok=True)
        n8n_path = f"/home/appuser/.n8n-files/{ts}_downloaded{os.path.splitext(final_path)[1]}"
        import shutil
        shutil.copy(final_path, n8n_path)
        os.remove(final_path)

        return jsonify({
            "file_path": n8n_path,
            "ts": ts,
            "status": "success"
        })

    except subprocess.TimeoutExpired:
        return jsonify({"error": "Download timeout"}), 500
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500
        
# ─── ENDPOINT: GET FILE ───────────────────────────────────────────────────────

@app.route("/api/get-file/<filename>", methods=["GET"])
def get_file(filename):
    try:
        from flask import send_file
        path = f"/home/appuser/.n8n-files/{filename}"
        if not os.path.exists(path):
            return jsonify({"error": "File not found", "path": path}), 404

        # نحدد الـ mimetype حسب امتداد الملف
        if filename.endswith(".mp3"):
            mimetype = "audio/mpeg"
        elif filename.endswith(".mp4"):
            mimetype = "video/mp4"
        else:
            mimetype = "application/octet-stream"

        return send_file(path, mimetype=mimetype)
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500 
        
# ─── ENDPOINT: SHEIKH VOICE EFFECT ───────────────────────────────────────────

@app.route("/api/sheikh-effect", methods=["POST"])
def sheikh_effect():
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        audio_file = request.files["file"]
        ts = str(uuid.uuid4().hex)[:8]

        in_path = os.path.join(AUDIO_DIR, f"{ts}_input.ogg")
        audio_file.save(in_path)

        # اسم الملف النهائي اللي هيتحط في نفس فولدر الفيديوهات
        out_filename = f"{ts}_sheikh.mp3"
        out_path = f"/home/appuser/.n8n-files/{out_filename}"
        os.makedirs("/home/appuser/.n8n-files", exist_ok=True)

        cmd = [
            "ffmpeg", "-y", "-i", in_path,
            "-af", "atempo=1.01,asetrate=44100*1.02,atempo=1.075,aecho=0.8:0.6:80:0.5,volume=2.0",
            "-c:a", "libmp3lame", "-b:a", "192k",
            out_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0 or not os.path.exists(out_path):
            return jsonify({"error": "ffmpeg failed", "stderr": result.stderr}), 500

        try:
            os.remove(in_path)
        except:
            pass

        return jsonify({
            "filename": out_filename,
            "ts": ts,
            "status": "success"
        })

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500
        
# ─── ENDPOINT prepare-quran-full ─────────────────────────────────────

import requests

BASE = "https://api.quran.com/api/v4"

# غيّرها للـ tafsir_id اللي عايزه (جيبه من /api/v4/resources/tafsirs)
# مثال: 169 = تفسير ابن كثير (مختصر) بالعربي
DEFAULT_TAFSIR_ID = 169


def download_file(url, filename):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    with open(filename, "wb") as f:
        f.write(r.content)
    return filename


@app.route("/api/prepare-quran-full", methods=["POST"])
def prepare_quran_full():
    data = request.get_json(force=True, silent=True)
    if data is None:
        return jsonify({"error": "invalid or missing JSON body"}), 400  
    surah = data.get("surah")
    start_ayah = int(data.get("startAyah"))
    end_ayah = int(data.get("endAyah"))
    reciter = int(data.get("reciterId", 7))
    tafsir_id = int(data.get("tafsirId", DEFAULT_TAFSIR_ID))

    full_data = []
    errors = []

    for ayah in range(start_ayah, end_ayah + 1):
        verse_key = f"{surah}:{ayah}"
        try:
            # 1. النص (بدون ترجمة بديلة عن التفسير)
            url_text = f"{BASE}/verses/by_key/{verse_key}?language=ar&words=false&fields=text_uthmani"
            r_text = requests.get(url_text, timeout=15)
            r_text.raise_for_status()
            verse_data = r_text.json()["verse"]

            # 2. التفسير الحقيقي - endpoint منفصل
            url_tafsir = f"{BASE}/tafsirs/{tafsir_id}/by_ayah/{verse_key}"
            r_tafsir = requests.get(url_tafsir, timeout=15)
            r_tafsir.raise_for_status()
            tafsir_text = r_tafsir.json()["tafsir"]["text"]

            # 3. الصوت + التوقيت - لازم fields عشان ترجع segments/duration/url
            url_timing = (
                f"{BASE}/quran/recitations/{reciter}"
                f"?verse_key={verse_key}&fields=segments,duration,url"
            )
            r_timing = requests.get(url_timing, timeout=15)
            r_timing.raise_for_status()
            audio_file = r_timing.json()["audio_files"][0]

            audio_url = audio_file["url"]
            if not audio_url.startswith("http"):
                audio_url = f"https://verses.quran.foundation/{audio_url}"

            filename = f"{surah}_{ayah}_{reciter}.mp3"
            download_file(audio_url, filename)

            # المدة الحقيقية بالميلي عن طريق ffprobe - متعتمدش على duration الراجعة من الـ API
            duration_ms = get_duration_ms_ffprobe(filename)

            full_data.append({
                "ayah_number": ayah,
                "verse_key": verse_key,
                "text_uthmani": verse_data["text_uthmani"],
                "tafsir": tafsir_text,
                "audio_path": filename,
                "duration_ms": duration_ms,
                "segments": audio_file.get("segments"),  # توقيت كل كلمة (لو متاح)
            })

        except Exception as e:
            # خطأ في آية واحدة مايوقفش باقي الحلقة
            errors.append({"ayah": ayah, "error": str(e)})
            continue

    # 4. احسب توقيت كل آية تراكميًا داخل الملف المجمّع (بالميلي)
    cumulative_ms = 0
    for item in full_data:
        item["start_ms"] = cumulative_ms
        cumulative_ms += item["duration_ms"]
        item["end_ms"] = cumulative_ms

    return jsonify({
        "data": full_data,
        "errors": errors,
        "status": "success" if full_data else "failed",
    })


def get_duration_ms_ffprobe(filename):
    import subprocess
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", filename],
        capture_output=True, text=True, check=True,
    )
    return int(float(result.stdout.strip()) * 1000)
    
 # ─── ENDPOINT: UPLOAD AUDIO (من n8n) ─────────────────────────────────────

from werkzeug.utils import secure_filename

@app.route("/api/upload-audio", methods=["POST"])
def upload_audio():
    """
    يستقبل ملف صوت مرفوع (multipart/form-data) من n8n ويحفظه على الديسك
    INPUT (form-data): file=<binary>, ts (اختياري), suffix (اختياري)
    OUTPUT: { audio_path, ts, suffix }
    """
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file part in request (expected field name 'file')"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "Empty filename"}), 400

        ts     = request.form.get("ts", str(uuid.uuid4())[:8])
        suffix = request.form.get("suffix", "audio")

        # الحفاظ على امتداد الملف الأصلي (mp3, ogg, wav...)
        ext = os.path.splitext(secure_filename(file.filename))[1] or ".mp3"

        os.makedirs(AUDIO_DIR, exist_ok=True)  # تأكد إن المتغير ده معرّف زي VIDEO_DIR
        audio_path = f"{AUDIO_DIR}/{ts}_{suffix}{ext}"
        file.save(audio_path)

        print(f"  Audio uploaded → {audio_path}")

        return jsonify({
            "audio_path": audio_path,
            "ts":         ts,
            "suffix":     suffix,
            "status":     "success"
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500
        
# ─── HEALTH ──────────────────────────────────────────────────────────────────

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "quran-worker"})

# ─── MAIN ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    os.makedirs(AUDIO_DIR, exist_ok=True)
    os.makedirs(VIDEO_DIR, exist_ok=True)
    os.makedirs(IMAGE_DIR, exist_ok=True)
    os.makedirs(FONT_DIR,  exist_ok=True)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 7860)), debug=False)