# /// script
# requires-python = ">=3.11,<3.12"
# dependencies = [
#   "huggingface-hub",
#   "numpy<2",
#   "pillow",
#   "requests",
#   "torch==2.1.2",
#   "torchvision==0.16.2",
#   "transformers==4.36.2",
# ]
# ///

"""Run a Swin2SR high-resolution inspection pilot for the top damage hotspots.

Swin2SR is used as the evidence-safer HF super-resolution baseline for visual
inspection chips. Raw and deterministic-enhanced imagery remain the evidence
layers; model output is a reviewed visual aid.
"""

from __future__ import annotations

import io
import json
import math
import os
import tarfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import requests
import torch
from huggingface_hub import HfApi
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
from transformers import AutoImageProcessor, Swin2SRForImageSuperResolution


OUTPUT_REPO = os.environ.get(
    "OUTPUT_REPO", "sergiopesch/ayudavenezuela2026-enhanced-satellite-tiles"
)
MODEL_ID = os.environ.get("SWIN2SR_MODEL_ID", "caidas/swin2SR-realworld-sr-x4-64-bsrgan-psnr")
OUTPUT_ROOT = Path(os.environ.get("SWIN2SR_OUTPUT_ROOT", "/tmp/swin2sr-satellite-pilot"))
ARCHIVE_NAME = os.environ.get(
    "SWIN2SR_ARCHIVE_NAME", "ayudavenezuela2026-swin2sr-worst-hotspots-z19-20260702.tar"
)
ARCHIVE_PATH = Path("/tmp") / ARCHIVE_NAME
CONTACT_SHEET_PATH = Path("/tmp/swin2sr-satellite-pilot-contact-sheet.jpg")
REPORT_PATH = Path("/tmp/swin2sr-satellite-pilot-report.json")
HOTSPOT_INDEX_PATH = Path(os.environ.get("SWIN2SR_HOTSPOT_INDEX", "public/data/worst-damage-hotspots.json"))
SR_ZOOM = int(os.environ.get("SWIN2SR_ZOOM", "19"))
AOI_LIMIT = int(os.environ.get("SWIN2SR_AOI_LIMIT", "3"))

SESSION = requests.Session()
SESSION.headers.update({"accept": "image/jpeg,*/*;q=0.8", "user-agent": "AyudaVenezuela2026 swin2sr pilot"})


@dataclass(frozen=True)
class Scene:
    key: str
    label: str
    cog_url: str


SCENES = {
    "before": Scene(
        key="before",
        label="Vantor LG02 pre-event imagery, 7 Apr 2026",
        cog_url="https://vantor-opendata.s3.amazonaws.com/events/Venezuela-Earthquake-Jun-2026/B120001100513B10.tif",
    ),
    "after": Scene(
        key="after",
        label="Vantor LG05 post-event imagery, 27 Jun 2026",
        cog_url="https://vantor-opendata.s3.amazonaws.com/events/Venezuela-Earthquake-Jun-2026/B15000110186C610.tif",
    ),
}

FALLBACK_HOTSPOTS = [
    {"id": "verified-hotspot-1", "rank": 1, "lon": -67.007108, "lat": 10.592425, "severity": "high"},
    {"id": "verified-hotspot-2", "rank": 2, "lon": -67.023908, "lat": 10.600825, "severity": "high"},
    {"id": "verified-hotspot-3", "rank": 3, "lon": -67.021508, "lat": 10.596025, "severity": "high"},
]


def lon_to_tile(lon: float, zoom: int) -> int:
    return math.floor(((lon + 180) / 360) * 2**zoom)


def lat_to_tile(lat: float, zoom: int) -> int:
    radians = math.radians(lat)
    return math.floor(((1 - math.log(math.tan(radians) + 1 / math.cos(radians)) / math.pi) / 2) * 2**zoom)


def tile_url(scene: Scene, zoom: int, x: int, y: int) -> str:
    from urllib.parse import quote

    return (
        "https://titiler.hotosm.org/cog/tiles/WebMercatorQuad/"
        f"{zoom}/{x}/{y}@2x?url={quote(scene.cog_url, safe='')}"
    )


def fetch_tile(scene: Scene, zoom: int, x: int, y: int) -> Image.Image | None:
    for attempt in range(1, 5):
        response = SESSION.get(tile_url(scene, zoom, x, y), timeout=45)
        if response.status_code == 404:
            return None
        if response.status_code in (429, 500, 502, 503, 504) and attempt < 4:
            time.sleep(0.6 * attempt**2)
            continue
        response.raise_for_status()
        data = response.content
        if len(data) <= 100 or data[:2] != b"\xff\xd8":
            return None
        image = Image.open(io.BytesIO(data)).convert("RGB")
        image.load()
        return image
    return None


def deterministic_enhance(image: Image.Image) -> Image.Image:
    enhanced = ImageEnhance.Contrast(image).enhance(1.08)
    enhanced = ImageEnhance.Color(enhanced).enhance(1.05)
    return enhanced.filter(ImageFilter.UnsharpMask(radius=0.8, percent=120, threshold=3))


def image_stats(image: Image.Image) -> dict[str, float | int]:
    values = np.asarray(image.convert("RGB"), dtype=np.float32)
    luma = values[..., 0] * 0.2126 + values[..., 1] * 0.7152 + values[..., 2] * 0.0722
    gy, gx = np.gradient(luma)
    return {
        "width": image.width,
        "height": image.height,
        "meanLuminance": round(float(luma.mean()), 3),
        "stddevLuminance": round(float(luma.std()), 3),
        "meanGradient": round(float(np.sqrt(gx * gx + gy * gy).mean()), 3),
    }


def save_jpeg(image: Image.Image, path: Path, quality: int = 92) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="JPEG", quality=quality, optimize=True)


def load_hotspots() -> list[dict]:
    if not HOTSPOT_INDEX_PATH.exists():
        return FALLBACK_HOTSPOTS[:AOI_LIMIT]
    data = json.loads(HOTSPOT_INDEX_PATH.read_text(encoding="utf-8"))
    hotspots = data.get("hotspots", [])
    if not hotspots:
        return FALLBACK_HOTSPOTS[:AOI_LIMIT]
    return [
        {
            "id": item.get("id", f"hotspot-{index:03d}"),
            "rank": item.get("rank", index),
            "lon": item["lng"],
            "lat": item["lat"],
            "severity": "high",
            "total": item.get("total"),
            "high": item.get("high"),
        }
        for index, item in enumerate(hotspots[:AOI_LIMIT], start=1)
    ]


def create_upsampler():
    processor = AutoImageProcessor.from_pretrained(MODEL_ID)
    model = Swin2SRForImageSuperResolution.from_pretrained(MODEL_ID)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device).eval()
    print(f"model={MODEL_ID} torch={torch.__version__} cuda={torch.cuda.is_available()} device={device}", flush=True)
    return processor, model, device


def run_swin2sr(processor, model, device, image: Image.Image) -> Image.Image:
    inputs = processor(image, return_tensors="pt").to(device)
    with torch.no_grad():
        reconstruction = model(**inputs).reconstruction.squeeze().float().cpu().clamp_(0, 1)
    output = reconstruction.numpy().transpose(1, 2, 0)
    return Image.fromarray((output * 255).round().astype(np.uint8), mode="RGB")


def build_contact_sheet(records: list[dict]) -> None:
    panel = 224
    label_height = 36
    columns = 6
    rows = len(records)
    sheet = Image.new("RGB", (columns * panel, rows * (panel + label_height)), "white")
    draw = ImageDraw.Draw(sheet)

    for row, record in enumerate(records):
        y = row * (panel + label_height)
        images = [
            ("before raw", Image.open(record["beforeRawPath"]).convert("RGB")),
            ("before Swin2SR", Image.open(record["beforeSrPath"]).convert("RGB")),
            ("after raw", Image.open(record["afterRawPath"]).convert("RGB")),
            ("after Swin2SR", Image.open(record["afterSrPath"]).convert("RGB")),
            ("before enhanced", Image.open(record["beforeEnhancedPath"]).convert("RGB")),
            ("after enhanced", Image.open(record["afterEnhancedPath"]).convert("RGB")),
        ]
        for column, (label, image) in enumerate(images):
            x = column * panel
            sheet.paste(image.resize((panel, panel)), (x, y))
            draw.text((x + 4, y + panel + 5), f"{record['id']} {label}", fill=(0, 0, 0))
    sheet.save(CONTACT_SHEET_PATH, format="JPEG", quality=88)


def create_archive() -> None:
    if ARCHIVE_PATH.exists():
        ARCHIVE_PATH.unlink()
    with tarfile.open(ARCHIVE_PATH, "w") as archive:
        archive.add(OUTPUT_ROOT, arcname="swin2sr-satellite-pilot")
        archive.add(REPORT_PATH, arcname="swin2sr-satellite-pilot/report.json")
        archive.add(CONTACT_SHEET_PATH, arcname="swin2sr-satellite-pilot/contact-sheet.jpg")
    print(f"archive: {ARCHIVE_PATH} bytes={ARCHIVE_PATH.stat().st_size}", flush=True)


def upload(path: Path, path_in_repo: str, message: str) -> None:
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise RuntimeError("HF_TOKEN missing from job environment")
    api = HfApi(token=token)
    info = api.upload_file(
        path_or_fileobj=str(path),
        path_in_repo=path_in_repo,
        repo_id=OUTPUT_REPO,
        repo_type="dataset",
        token=token,
        commit_message=message,
    )
    print(f"uploaded {path_in_repo}: {info}", flush=True)


def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    processor, model, device = create_upsampler()
    records: list[dict] = []

    for hotspot in load_hotspots():
        tile_x = lon_to_tile(hotspot["lon"], SR_ZOOM)
        tile_y = lat_to_tile(hotspot["lat"], SR_ZOOM)
        record = {
            "id": hotspot["id"],
            **hotspot,
            "zoom": SR_ZOOM,
            "tile": {"x": tile_x, "y": tile_y},
            "model": MODEL_ID,
            "interpretive": True,
            "warning": "Swin2SR output is a visual inspection aid; compare against raw source before decisions.",
            "scenes": {},
        }

        for scene_key, scene in SCENES.items():
            raw = fetch_tile(scene, SR_ZOOM, tile_x, tile_y)
            if raw is None:
                record["scenes"][scene_key] = {"available": False}
                continue
            enhanced = deterministic_enhance(raw)
            sr = run_swin2sr(processor, model, device, raw)
            scene_dir = OUTPUT_ROOT / record["id"] / scene_key
            raw_path = scene_dir / "raw-z19-512.jpg"
            enhanced_path = scene_dir / "deterministic-enhanced-z19-512.jpg"
            sr_path = scene_dir / "swin2sr-x4-z19.jpg"
            save_jpeg(raw, raw_path, 94)
            save_jpeg(enhanced, enhanced_path, 94)
            save_jpeg(sr, sr_path, 92)
            record["scenes"][scene_key] = {
                "available": True,
                "rawPath": str(raw_path),
                "enhancedPath": str(enhanced_path),
                "srPath": str(sr_path),
                "rawStats": image_stats(raw),
                "enhancedStats": image_stats(enhanced),
                "srStats": image_stats(sr),
            }
            record[f"{scene_key}RawPath"] = str(raw_path)
            record[f"{scene_key}EnhancedPath"] = str(enhanced_path)
            record[f"{scene_key}SrPath"] = str(sr_path)

        if record["scenes"].get("before", {}).get("available") and record["scenes"].get("after", {}).get("available"):
            records.append(record)
            print(f"processed {record['id']} tile={tile_x}/{tile_y}", flush=True)
        else:
            print(f"skipped {record['id']} missing before/after tile", flush=True)

    build_contact_sheet(records)
    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "type": "swin2sr-super-resolution-pilot",
        "model": {
            "name": MODEL_ID,
            "scale": 4,
            "source": f"https://huggingface.co/{MODEL_ID}",
            "learned": True,
            "hallucinationRisk": "lower than diffusion/GAN, still nonzero",
        },
        "source": {
            "before": SCENES["before"].__dict__,
            "after": SCENES["after"].__dict__,
            "hotspots": str(HOTSPOT_INDEX_PATH),
        },
        "zoom": SR_ZOOM,
        "requestedAois": AOI_LIMIT,
        "completedAois": len(records),
        "records": records,
        "useGuidance": "Interpretive visual aid only. Use raw and deterministic enhanced imagery as evidence layers.",
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    create_archive()
    upload(REPORT_PATH, "super-resolution/swin2sr-pilot/report-20260702.json", "Add Swin2SR satellite SR pilot report")
    upload(CONTACT_SHEET_PATH, "super-resolution/swin2sr-pilot/contact-sheet-20260702.jpg", "Add Swin2SR satellite SR pilot contact sheet")
    upload(ARCHIVE_PATH, f"super-resolution/swin2sr-pilot/{ARCHIVE_NAME}", "Add Swin2SR satellite SR pilot archive")


if __name__ == "__main__":
    main()
