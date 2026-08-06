"""
MHTML extraction core.
- Parses MHTML, extracts embedded images, validates them, builds a ZIP.
- Supports a progress_callback(stage: str, percent: int, message: str) for live progress.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import unquote, unquote_to_bytes

IMAGE_EXT_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/avif": ".avif",
    "image/tiff": ".tif",
    "image/svg+xml": ".svg",
}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif", ".tif", ".tiff", ".svg"}

# magic-byte signatures used to verify the bytes are actually a real image,
# not a truncated/corrupted part that just happens to carry an image/* mime type.
MAGIC_SIGNATURES = [
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"RIFF", "image/webp"),  # followed by WEBP at offset 8, checked separately
    (b"BM", "image/bmp"),
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
]

ProgressCB = Optional[Callable[[str, int, str], None]]


def _report(cb: ProgressCB, stage: str, percent: int, message: str):
    if cb:
        cb(stage, percent, message)


def is_valid_image_bytes(data: bytes, mime: str) -> bool:
    """Verify bytes look like a real image using magic-byte signatures.
    SVG is XML text so it's checked separately. Falls back to a lenient
    'non-empty' check for unrecognized-but-declared image types.
    """
    if not data:
        return False
    if mime == "image/svg+xml":
        head = data[:200].lstrip().lower()
        return head.startswith(b"<svg") or b"<svg" in head
    for sig, sig_mime in MAGIC_SIGNATURES:
        if data.startswith(sig):
            if sig_mime == "image/webp":
                return data[8:12] == b"WEBP"
            return True
    # Unknown signature: accept only if it's reasonably sized (avoid 0/near-empty junk)
    return len(data) > 64


@dataclass
class ExtractedImage:
    filename: str
    content_type: str
    data: bytes
    source: str
    valid: bool


class ImgSrcCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sources: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "img":
            return
        attrs_map = dict(attrs)
        src = attrs_map.get("src")
        if src:
            self.sources.append(src.strip())


def normalize_cid(value: str) -> str:
    return value.strip().strip("<>").strip().lower()


def safe_stem(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\u0600-\u06FF._-]+", "_", name.strip())
    cleaned = cleaned.strip("._-")
    return cleaned or "chapter"


def extension_for_part(content_type: str, filename: Optional[str] = None) -> str:
    if filename:
        ext = Path(filename).suffix.lower()
        if ext in IMAGE_EXTS:
            return ".jpg" if ext == ".jpeg" else ext
    if content_type in IMAGE_EXT_BY_MIME:
        return IMAGE_EXT_BY_MIME[content_type]
    guessed = mimetypes.guess_extension(content_type.split(";")[0].strip().lower() or "")
    if guessed:
        return ".jpg" if guessed == ".jpe" else guessed
    return ".bin"


def decode_data_uri(uri: str) -> Tuple[bytes, str]:
    header, _, payload = uri.partition(",")
    if not header.startswith("data:"):
        raise ValueError("Not a data URI")
    meta = header[5:]
    mime = "text/plain"
    is_base64 = False
    if meta:
        parts = meta.split(";")
        if parts and parts[0] and "/" in parts[0]:
            mime = parts[0].strip().lower()
            parts = parts[1:]
        for p in parts:
            if p.lower() == "base64":
                is_base64 = True
    if is_base64:
        return base64.b64decode(payload), mime
    return unquote_to_bytes(payload), mime


class _Part:
    def __init__(self, index: int, content_type: str, content_id: str, filename: Optional[str], data: bytes):
        self.index = index
        self.content_type = content_type
        self.content_id = normalize_cid(content_id)
        self.filename = filename
        self.data = data
        self.is_image = (
            content_type.startswith("image/")
            or (filename is not None and Path(filename).suffix.lower() in IMAGE_EXTS)
        )

    def source_name(self) -> str:
        if self.filename:
            return self.filename
        if self.content_id:
            return self.content_id
        return f"part_{self.index}"


class ExtractionError(Exception):
    pass


def parse_mhtml(path: Path, cb: ProgressCB = None) -> Tuple[Optional[str], List[_Part]]:
    _report(cb, "parsing", 5, "قراءة ملف MHTML...")
    raw = path.read_bytes()
    if not raw.strip():
        raise ExtractionError("الملف فارغ.")

    try:
        msg = BytesParser(policy=policy.default).parsebytes(raw)
    except Exception as e:
        raise ExtractionError(f"تعذر تحليل بنية MHTML: {e}")

    html_text: Optional[str] = None
    parts: List[_Part] = []

    _report(cb, "parsing", 15, "استخراج الأجزاء (parts)...")
    index = 0
    for part in msg.walk():
        if part.is_multipart():
            continue
        content_type = part.get_content_type()
        try:
            payload = part.get_payload(decode=True) or b""
        except Exception:
            payload = b""
        content_id = part.get("Content-ID", "") or ""
        filename = part.get_filename()

        if content_type == "text/html" and html_text is None:
            charset = part.get_content_charset() or "utf-8"
            try:
                html_text = payload.decode(charset, errors="replace")
            except LookupError:
                html_text = payload.decode("utf-8", errors="replace")
            continue

        if content_type.startswith("image/") or filename or content_id:
            parts.append(_Part(index, content_type, content_id, filename, payload))
            index += 1

    if html_text is None and not parts:
        raise ExtractionError("لم يتم العثور على محتوى HTML ولا أي أجزاء داخل الملف. تأكد أن الملف MHTML صالح.")

    return html_text, parts


def collect_ordered_images(html_text: Optional[str], parts: List[_Part], cb: ProgressCB = None) -> Tuple[List[ExtractedImage], dict]:
    cid_map: Dict[str, _Part] = {}
    filename_map: Dict[str, List[_Part]] = {}
    for part in parts:
        if part.content_id:
            cid_map[part.content_id] = part
        if part.filename:
            filename_map.setdefault(Path(part.filename).name.lower(), []).append(part)

    used: set[int] = set()
    extracted: List[ExtractedImage] = []
    stats = {"img_tags_found": 0, "matched_from_html": 0, "unmatched_img_tags": 0, "fallback_parts_added": 0, "invalid_images_skipped": 0}

    def add_part(part: _Part, source: str):
        if part.index in used:
            return
        used.add(part.index)
        ext = extension_for_part(part.content_type, part.filename)
        valid = is_valid_image_bytes(part.data, part.content_type)
        if not valid:
            stats["invalid_images_skipped"] += 1
            return
        extracted.append(ExtractedImage(f"{len(extracted)+1:03d}{ext}", part.content_type, part.data, source, valid))

    def add_bytes(data: bytes, mime: str, source: str):
        ext = extension_for_part(mime)
        valid = is_valid_image_bytes(data, mime)
        if not valid:
            stats["invalid_images_skipped"] += 1
            return
        extracted.append(ExtractedImage(f"{len(extracted)+1:03d}{ext}", mime, data, source, valid))

    if html_text:
        _report(cb, "matching", 30, "مطابقة ترتيب الصور من HTML...")
        parser = ImgSrcCollector()
        parser.feed(html_text)
        stats["img_tags_found"] = len(parser.sources)

        for src in parser.sources:
            clean_src = src.strip()
            matched = False

            if clean_src.lower().startswith("cid:"):
                cid = normalize_cid(clean_src[4:])
                part = cid_map.get(cid)
                if part:
                    before = len(extracted)
                    add_part(part, f"cid:{cid}")
                    matched = len(extracted) > before or part.index in used
            elif clean_src.lower().startswith("data:"):
                try:
                    data, mime = decode_data_uri(clean_src)
                    before = len(extracted)
                    add_bytes(data, mime, "data:")
                    matched = len(extracted) > before
                except Exception:
                    matched = False
            else:
                base_name = unquote(Path(clean_src).name).lower()
                if base_name in filename_map:
                    for part in filename_map[base_name]:
                        add_part(part, clean_src)
                    matched = True

            if matched:
                stats["matched_from_html"] += 1
            else:
                stats["unmatched_img_tags"] += 1

    _report(cb, "fallback", 55, "إضافة أي صور متبقية لم تُذكر صراحة في HTML...")
    for part in sorted(parts, key=lambda p: p.index):
        if part.index in used:
            continue
        if part.is_image:
            before = len(extracted)
            add_part(part, part.source_name())
            if len(extracted) > before:
                stats["fallback_parts_added"] += 1

    normalized: List[ExtractedImage] = []
    for i, item in enumerate(extracted, start=1):
        ext = Path(item.filename).suffix or extension_for_part(item.content_type)
        normalized.append(ExtractedImage(f"{i:03d}{ext}", item.content_type, item.data, item.source, item.valid))
    return normalized, stats


def build_zip(out_zip: Path, base_name: str, images: List[ExtractedImage], source_file: Path, stats: dict, cb: ProgressCB = None) -> dict:
    out_zip.parent.mkdir(parents=True, exist_ok=True)

    manifest = {
        "source_file": source_file.name,
        "image_count": len(images),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "stats": stats,
        "items": [
            {"filename": img.filename, "content_type": img.content_type, "source": img.source, "bytes": len(img.data)}
            for img in images
        ],
    }

    _report(cb, "packing", 80, "بناء ملف ZIP...")
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{base_name}/manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        total = len(images) or 1
        for i, img in enumerate(images, start=1):
            zf.writestr(f"{base_name}/{img.filename}", img.data)
            if i % 5 == 0 or i == total:
                pct = 80 + int(15 * i / total)
                _report(cb, "packing", min(pct, 95), f"إضافة الصور إلى الأرشيف ({i}/{total})...")

    _report(cb, "done", 100, "اكتمل الاستخراج.")
    return manifest


def extract_mhtml_to_zip(input_path: Path, output_zip: Path, base_name: Optional[str] = None, cb: ProgressCB = None) -> dict:
    """Full pipeline. Raises ExtractionError on failure. Returns the manifest dict on success."""
    if input_path.suffix.lower() not in {".mhtml", ".mht"}:
        _report(cb, "warning", 2, "تنبيه: امتداد الملف ليس mhtml/mht، سيتم المحاولة على أي حال.")

    html_text, parts = parse_mhtml(input_path, cb)
    images, stats = collect_ordered_images(html_text, parts, cb)

    if not images:
        raise ExtractionError(
            "لم يتم العثور على أي صور صالحة داخل الملف. غالباً الموقع يخزّن روابط صور خارجية فقط ولم يتم تضمينها داخل MHTML."
        )

    folder_name = safe_stem(base_name or input_path.stem)
    manifest = build_zip(output_zip, folder_name, images, input_path, stats, cb)
    return manifest
