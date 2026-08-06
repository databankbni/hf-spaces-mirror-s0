"""
renamer.py
إعادة ترقيم أسماء الصور داخل ملف ZIP إلى تسلسل منظم (001, 002, 003...).
- يدعم المسافات والأحرف العربية/اليابانية والرموز والأقواس
- يرتب حسب الأرقام الموجودة بالاسم إذا وُجدت، وإلا أبجدياً
- يتجاهل: الملفات غير الصورية، .DS_Store، __MACOSX، Thumbs.db، ملفات النظام
- لا يعدل محتوى الصور أو يضغطها
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, List, Optional

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif"}

ProgressCB = Optional[Callable[[str, int, str], None]]


def _report(cb: ProgressCB, stage: str, percent: int, message: str):
    if cb:
        cb(stage, percent, message)


class RenamerError(Exception):
    pass


def _is_junk_path(name: str) -> bool:
    """يستبعد ملفات النظام والمجلدات المخفية."""
    parts = PurePosixPath(name).parts
    for part in parts:
        if part.startswith("."):
            return True
        if part.lower() in {"__macosx", "thumbs.db", "desktop.ini"}:
            return True
    return False


def _extract_sort_key(name: str):
    """
    مفتاح الترتيب:
    - لو الاسم يحتوي على أرقام → نرتب حسب أول رقم (طبيعي/numeric)
    - وإلا → نرتب أبجدياً بالاسم كله
    مثال: '10.jpg', '2.jpg', '100.jpg' → [2, 10, 100]
    """
    stem = Path(name).stem
    nums = re.findall(r"\d+", stem)
    if nums:
        # أول رقم هو المفتاح الرئيسي، الباقي ثانوي
        return (0, int(nums[0]), stem.lower())
    return (1, 0, stem.lower())


@dataclass
class RenamedImage:
    original_name: str   # الاسم داخل ZIP الأصلي
    new_name: str        # الاسم الجديد (001.jpg, 002.png...)
    data: bytes          # محتوى الصورة بدون تعديل
    ext: str             # الامتداد


def rename_zip_images(
    input_zip: Path,
    output_zip: Path,
    cb: ProgressCB = None,
) -> dict:
    """
    القناة الرئيسية:
    1. يفتح ZIP
    2. يجمع الصور ويفلتر الجانك
    3. يرتبها
    4. يعيد ترقيمها
    5. يبني ZIP جديد
    يرجع dict بإحصائيات العملية.
    """
    _report(cb, "reading", 5, "قراءة ملف ZIP...")

    # ─── التحقق من صحة الملف ──────────────────────────────────
    if not zipfile.is_zipfile(input_zip):
        raise RenamerError("الملف ليس ZIP صالحاً أو أنه تالف.")

    # ─── جمع الصور ────────────────────────────────────────────
    _report(cb, "scanning", 15, "فحص محتوى ZIP...")

    images: List[RenamedImage] = []
    skipped_junk = 0
    skipped_non_image = 0

    try:
        with zipfile.ZipFile(input_zip, "r") as zf:
            all_names = zf.namelist()
            total = len(all_names)

            for i, name in enumerate(all_names):
                # تجاهل المجلدات
                if name.endswith("/"):
                    skipped_non_image += 1
                    continue

                # تجاهل ملفات النظام والمخفية
                if _is_junk_path(name):
                    skipped_junk += 1
                    continue

                ext = Path(name).suffix.lower()
                if ext == ".jpeg":
                    ext = ".jpg"

                # تجاهل غير الصور
                if ext not in IMAGE_EXTS:
                    skipped_non_image += 1
                    continue

                try:
                    data = zf.read(name)
                except Exception:
                    skipped_junk += 1
                    continue

                # اسم الملف بدون مسار المجلد
                base = Path(name).name
                images.append(RenamedImage(
                    original_name=name,
                    new_name="",   # يتحدد بعد الترتيب
                    data=data,
                    ext=ext,
                ))

                if i % 10 == 0:
                    pct = 15 + int(25 * i / max(total, 1))
                    _report(cb, "scanning", pct, f"فحص الملفات ({i+1}/{total})...")

    except zipfile.BadZipFile:
        raise RenamerError("ملف ZIP تالف أو غير قابل للقراءة.")
    except Exception as e:
        raise RenamerError(f"خطأ أثناء قراءة ZIP: {e}")

    if not images:
        raise RenamerError(
            "لم يتم العثور على أي صور داخل ZIP. "
            "تأكد أن الملف يحتوي على صور بصيغ: jpg, png, webp, gif, bmp, avif."
        )

    # ─── الترتيب ──────────────────────────────────────────────
    _report(cb, "sorting", 45, f"ترتيب {len(images)} صورة...")

    images.sort(key=lambda img: _extract_sort_key(img.original_name))

    # ─── إعادة الترقيم ────────────────────────────────────────
    padding = max(3, len(str(len(images))))   # على الأقل 3 خانات (001)
    for idx, img in enumerate(images, start=1):
        img.new_name = f"{str(idx).zfill(padding)}{img.ext}"

    # ─── بناء ZIP الجديد ──────────────────────────────────────
    _report(cb, "packing", 55, "بناء ZIP الجديد...")

    output_zip.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_STORED) as zf:
            for i, img in enumerate(images, start=1):
                zf.writestr(img.new_name, img.data)
                if i % 5 == 0 or i == len(images):
                    pct = 55 + int(40 * i / len(images))
                    _report(cb, "packing", min(pct, 95), f"إضافة الصور ({i}/{len(images)})...")
    except Exception as e:
        raise RenamerError(f"فشل إنشاء ZIP الجديد: {e}")

    _report(cb, "done", 100, "تمت إعادة الترتيب بنجاح.")

    return {
        "image_count": len(images),
        "skipped_junk": skipped_junk,
        "skipped_non_image": skipped_non_image,
        "items": [
            {"original": img.original_name, "renamed": img.new_name}
            for img in images
        ],
    }
