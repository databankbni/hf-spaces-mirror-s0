# /// script
# requires-python = ">=3.11,<3.12"
# dependencies = [
#   "basicsr==1.4.2",
#   "huggingface-hub",
#   "numpy<2",
#   "opencv-python-headless",
#   "pillow",
#   "realesrgan==0.3.0",
#   "requests",
#   "torch==2.1.2",
#   "torchvision==0.16.2",
# ]
# ///

"""Run a damage-focused Real-ESRGAN pilot for satellite before/after imagery.

This is intentionally separate from the deterministic enhanced-tile pipeline.
Real-ESRGAN is learned super-resolution and may hallucinate texture. Outputs are
for interpretive visual review only, not evidence replacement.
"""

from __future__ import annotations

import io
import base64
import json
import math
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import requests
from huggingface_hub import HfApi
from PIL import Image, ImageDraw


OUTPUT_REPO = os.environ.get(
    "OUTPUT_REPO", "sergiopesch/ayudavenezuela2026-enhanced-satellite-tiles"
)
OUTPUT_ROOT = Path(os.environ.get("SR_OUTPUT_ROOT", "/tmp/satellite-super-resolution-pilot"))
ARCHIVE_NAME = os.environ.get(
    "SR_ARCHIVE_NAME", "ayudavenezuela2026-real-esrgan-satellite-pilot-20260702.tar"
)
ARCHIVE_PATH = Path("/tmp") / ARCHIVE_NAME
AOI_LIMIT = int(os.environ.get("SR_AOI_LIMIT", "12"))
SR_ZOOM = int(os.environ.get("SR_ZOOM", "19"))
MODEL_URL = os.environ.get(
    "SR_MODEL_URL",
    "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
)
MODEL_PATH = Path("/tmp/RealESRGAN_x4plus.pth")
CONTACT_SHEET_PATH = Path("/tmp/real-esrgan-satellite-pilot-contact-sheet.jpg")
REPORT_PATH = Path("/tmp/real-esrgan-satellite-pilot-report.json")

SESSION = requests.Session()
SESSION.headers.update({"accept": "image/jpeg,*/*;q=0.8", "user-agent": "AyudaVenezuela2026 real-esrgan pilot"})


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

FALLBACK_DAMAGE_AOIS = [
    {"lon": -67.032311, "lat": 10.582148, "severityCode": 0, "severity": "high"},
    {"lon": -67.034816, "lat": 10.582792, "severityCode": 0, "severity": "high"},
    {"lon": -67.033328, "lat": 10.585053, "severityCode": 0, "severity": "high"},
    {"lon": -67.032311, "lat": 10.586657, "severityCode": 0, "severity": "high"},
    {"lon": -67.034164, "lat": 10.587451, "severityCode": 0, "severity": "high"},
    {"lon": -67.034609, "lat": 10.593642, "severityCode": 0, "severity": "high"},
    {"lon": -67.032702, "lat": 10.599287, "severityCode": 0, "severity": "high"},
    {"lon": -67.033661, "lat": 10.601445, "severityCode": 0, "severity": "high"},
    {"lon": -67.03232, "lat": 10.602165, "severityCode": 0, "severity": "high"},
    {"lon": -67.034959, "lat": 10.603203, "severityCode": 0, "severity": "high"},
    {"lon": -67.032855, "lat": 10.604039, "severityCode": 0, "severity": "high"},
    {"lon": -67.034262, "lat": 10.604878, "severityCode": 0, "severity": "high"},
    {"lon": -67.032004, "lat": 10.605498, "severityCode": 0, "severity": "high"},
    {"lon": -67.033414, "lat": 10.606185, "severityCode": 0, "severity": "high"},
    {"lon": -67.034793, "lat": 10.607132, "severityCode": 0, "severity": "high"},
    {"lon": -67.032035, "lat": 10.607487, "severityCode": 0, "severity": "high"},
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
    import cv2

    arr = np.asarray(image.convert("RGB"), dtype=np.uint8)
    lab = cv2.cvtColor(arr, cv2.COLOR_RGB2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8))
    l2 = clahe.apply(l)
    merged = cv2.merge([l2, a, b])
    rgb = cv2.cvtColor(merged, cv2.COLOR_LAB2RGB)
    blur = cv2.GaussianBlur(rgb, (0, 0), 0.8)
    sharp = cv2.addWeighted(rgb, 1.18, blur, -0.18, 0)
    return Image.fromarray(sharp)


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


def load_damage_aois() -> list[dict]:
    encoded_aois = os.environ.get("SR_AOIS_JSON_B64")
    if encoded_aois:
        payload = base64.b64decode(encoded_aois).decode("utf-8")
        aois = json.loads(payload)
        if not isinstance(aois, list) or not aois:
            raise RuntimeError("SR_AOIS_JSON_B64 did not decode to a non-empty AOI list")
        return aois[:AOI_LIMIT]

    inline_aois = os.environ.get("SR_AOIS_JSON")
    if inline_aois:
        aois = json.loads(inline_aois)
        if not isinstance(aois, list) or not aois:
            raise RuntimeError("SR_AOIS_JSON did not decode to a non-empty AOI list")
        return aois[:AOI_LIMIT]

    index_path = Path("public/data/damage-view-index.json")
    if not index_path.exists():
        return FALLBACK_DAMAGE_AOIS[:AOI_LIMIT]
    data = json.loads(index_path.read_text(encoding="utf-8"))
    severity_rank = {0: 0, 1: 1, 2: 2, 3: 3}
    candidates = [
        {"lon": lon, "lat": lat, "severityCode": int(severity), "severity": data["severityCodes"][str(severity)]}
        for lon, lat, severity in data["points"]
        if int(severity) in (0, 1)
    ]
    candidates.sort(key=lambda item: (severity_rank[item["severityCode"]], item["lon"], item["lat"]))

    selected: list[dict] = []
    min_distance = 0.0012
    for item in candidates:
        if all(abs(item["lon"] - other["lon"]) + abs(item["lat"] - other["lat"]) >= min_distance for other in selected):
            selected.append(item)
        if len(selected) >= AOI_LIMIT:
            break
    return selected


def download_model() -> None:
    if MODEL_PATH.exists() and MODEL_PATH.stat().st_size > 1_000_000:
        return
    print(f"downloading model: {MODEL_URL}", flush=True)
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    print(f"model bytes: {MODEL_PATH.stat().st_size}", flush=True)


def ensure_headless_opencv() -> None:
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("uv is required to patch OpenCV in the Jobs environment")
    subprocess.run([uv, "pip", "uninstall", "--python", sys.executable, "opencv-python"], check=False)
    subprocess.run(
        [
            uv,
            "pip",
            "install",
            "--python",
            sys.executable,
            "--force-reinstall",
            "--no-deps",
            "opencv-python-headless==4.11.0.86",
        ],
        check=True,
    )


def create_upsampler():
    import torch
    from basicsr.archs.rrdbnet_arch import RRDBNet
    from realesrgan import RealESRGANer

    download_model()
    model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"torch={torch.__version__} cuda={torch.cuda.is_available()} device={device}", flush=True)
    return RealESRGANer(
        scale=4,
        model_path=str(MODEL_PATH),
        model=model,
        tile=256,
        tile_pad=24,
        pre_pad=0,
        half=torch.cuda.is_available(),
        device=device,
    )


def run_sr(upsampler: RealESRGANer, image: Image.Image) -> Image.Image:
    import cv2

    input_bgr = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2BGR)
    output_bgr, _ = upsampler.enhance(input_bgr, outscale=4)
    output_rgb = cv2.cvtColor(output_bgr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(output_rgb)


def build_contact_sheet(records: list[dict]) -> None:
    panel = 220
    label_height = 34
    columns = 6
    rows = len(records)
    sheet = Image.new("RGB", (columns * panel, rows * (panel + label_height)), "white")
    draw = ImageDraw.Draw(sheet)

    for row, record in enumerate(records):
        y = row * (panel + label_height)
        images = [
            ("before raw", Image.open(record["beforeRawPath"]).convert("RGB")),
            ("before SR", Image.open(record["beforeSrPath"]).convert("RGB")),
            ("after raw", Image.open(record["afterRawPath"]).convert("RGB")),
            ("after SR", Image.open(record["afterSrPath"]).convert("RGB")),
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
        archive.add(OUTPUT_ROOT, arcname="real-esrgan-satellite-pilot")
        archive.add(REPORT_PATH, arcname="real-esrgan-satellite-pilot/report.json")
        archive.add(CONTACT_SHEET_PATH, arcname="real-esrgan-satellite-pilot/contact-sheet.jpg")
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
    ensure_headless_opencv()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    upsampler = create_upsampler()
    aois = load_damage_aois()
    records: list[dict] = []

    for index, aoi in enumerate(aois, start=1):
        tile_x = lon_to_tile(aoi["lon"], SR_ZOOM)
        tile_y = lat_to_tile(aoi["lat"], SR_ZOOM)
        record = {
            "id": f"aoi-{index:03d}",
            **aoi,
            "zoom": SR_ZOOM,
            "tile": {"x": tile_x, "y": tile_y},
            "model": "RealESRGAN_x4plus",
            "interpretive": True,
            "warning": "Learned super-resolution can hallucinate texture; compare against raw source before using for decisions.",
            "scenes": {},
        }

        for scene_key, scene in SCENES.items():
            raw = fetch_tile(scene, SR_ZOOM, tile_x, tile_y)
            if raw is None:
                record["scenes"][scene_key] = {"available": False}
                continue
            enhanced = deterministic_enhance(raw)
            sr = run_sr(upsampler, raw)
            scene_dir = OUTPUT_ROOT / record["id"] / scene_key
            raw_path = scene_dir / "raw-z19-512.jpg"
            enhanced_path = scene_dir / "deterministic-enhanced-z19-512.jpg"
            sr_path = scene_dir / "real-esrgan-x4-z19-2048.jpg"
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
            print(f"processed {record['id']} tile={tile_x}/{tile_y} severity={aoi['severity']}", flush=True)
        else:
            print(f"skipped {record['id']} missing before/after tile", flush=True)

    build_contact_sheet(records)
    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "type": "true-super-resolution-pilot",
        "model": {
            "name": "RealESRGAN_x4plus",
            "scale": 4,
            "source": MODEL_URL,
            "learned": True,
            "hallucinationRisk": "nonzero",
        },
        "source": {
            "before": SCENES["before"].__dict__,
            "after": SCENES["after"].__dict__,
            "damageIndex": "public/data/damage-view-index.json",
        },
        "zoom": SR_ZOOM,
        "requestedAois": AOI_LIMIT,
        "completedAois": len(records),
        "records": records,
        "useGuidance": "Interpretive visual aid only. Use raw and deterministic enhanced imagery as evidence layers.",
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    create_archive()
    upload(REPORT_PATH, "super-resolution/real-esrgan-pilot/report-20260702.json", "Add Real-ESRGAN satellite SR pilot report")
    upload(CONTACT_SHEET_PATH, "super-resolution/real-esrgan-pilot/contact-sheet-20260702.jpg", "Add Real-ESRGAN satellite SR pilot contact sheet")
    upload(ARCHIVE_PATH, f"super-resolution/real-esrgan-pilot/{ARCHIVE_NAME}", "Add Real-ESRGAN satellite SR pilot archive")


if __name__ == "__main__":
    main()
