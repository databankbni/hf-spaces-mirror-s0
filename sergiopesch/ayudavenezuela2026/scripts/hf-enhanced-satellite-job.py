# /// script
# dependencies = ["huggingface-hub", "numpy", "Pillow", "requests"]
# ///

"""Generate enhanced satellite tiles on Hugging Face Jobs and persist an archive.

The enhancement is deterministic and non-generative. It fetches 512 px Vantor STAC COG
source tiles, computes scene-level luminance calibration, applies conservative
sharpen/color adjustments, and uploads a tar archive plus manifest to a Hub dataset.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import tarfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import requests
from huggingface_hub import HfApi, whoami
from PIL import Image


OUTPUT_REPO = os.environ.get(
    "OUTPUT_REPO", "sergiopesch/ayudavenezuela2026-enhanced-satellite-tiles"
)
OUTPUT_ROOT = Path(os.environ.get("ENHANCED_TILE_ROOT", "/tmp/enhanced-satellite-tiles"))
ARCHIVE_PATH = Path(os.environ.get("ENHANCED_TILE_ARCHIVE", "/tmp/enhanced-satellite-tiles.tar"))
ZOOM_LEVELS = [
    int(value.strip())
    for value in os.environ.get("ENHANCED_TILE_ZOOMS", "18,19").split(",")
    if value.strip()
]
CONCURRENCY = max(1, int(os.environ.get("ENHANCED_TILE_CONCURRENCY", "36")))
JPEG_QUALITY = max(70, min(98, int(os.environ.get("ENHANCED_TILE_QUALITY", "92"))))
CALIBRATION_TILE_COUNT = max(8, int(os.environ.get("ENHANCED_TILE_CALIBRATION_TILES", "128")))
SMOKE_LIMIT = int(os.environ.get("ENHANCED_TILE_LIMIT", "0"))

SESSION = requests.Session()
SESSION.headers.update({"accept": "image/jpeg,*/*;q=0.8", "user-agent": "AyudaVenezuela2026 tile enhancer"})


@dataclass(frozen=True)
class Bounds:
    west: float
    south: float
    east: float
    north: float


@dataclass(frozen=True)
class Scene:
    key: str
    label: str
    cog_url: str
    bounds: Bounds
    gsd_meters: float


SCENES = {
    "before": Scene(
        key="before",
        label="Vantor LG02 pre-event imagery, 7 Apr 2026",
        cog_url="https://vantor-opendata.s3.amazonaws.com/events/Venezuela-Earthquake-Jun-2026/B120001100513B10.tif",
        bounds=Bounds(west=-67.085575, south=10.518145, east=-66.967422, north=10.679827),
        gsd_meters=0.415,
    ),
    "after": Scene(
        key="after",
        label="Vantor LG05 post-event imagery, 27 Jun 2026",
        cog_url="https://vantor-opendata.s3.amazonaws.com/events/Venezuela-Earthquake-Jun-2026/B15000110186C610.tif",
        bounds=Bounds(west=-67.043108, south=10.524025, east=-66.942944, north=10.642557),
        gsd_meters=0.3494610093253814,
    ),
}

VERIFIED_DAMAGE_BOUNDS = Bounds(west=-67.14, south=10.54, east=-66.96, north=10.65)


def intersect_bounds(*bounds_list: Bounds) -> Bounds:
    return Bounds(
        west=max(bounds.west for bounds in bounds_list),
        south=max(bounds.south for bounds in bounds_list),
        east=min(bounds.east for bounds in bounds_list),
        north=min(bounds.north for bounds in bounds_list),
    )


ENHANCED_BOUNDS = intersect_bounds(
    VERIFIED_DAMAGE_BOUNDS, SCENES["before"].bounds, SCENES["after"].bounds
)


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


def tiles_for_bounds(bounds: Bounds, zoom: int) -> list[tuple[int, int, int]]:
    min_x = lon_to_tile(bounds.west, zoom)
    max_x = lon_to_tile(bounds.east, zoom)
    min_y = lat_to_tile(bounds.north, zoom)
    max_y = lat_to_tile(bounds.south, zoom)
    return [(zoom, x, y) for x in range(min_x, max_x + 1) for y in range(min_y, max_y + 1)]


def fetch_tile(scene: Scene, zoom: int, x: int, y: int) -> bytes | None:
    url = tile_url(scene, zoom, x, y)
    for attempt in range(1, 5):
        response = SESSION.get(url, timeout=45)
        if response.status_code == 404:
            return None
        if response.status_code in (429, 500, 502, 503, 504) and attempt < 4:
            time.sleep(0.45 * attempt**2)
            continue
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        data = response.content
        if "image" not in content_type or len(data) <= 100 or data[:2] != b"\xff\xd8":
            return None
        return data
    return None


def decode_rgb(tile: bytes) -> np.ndarray:
    with Image.open(io.BytesIO(tile)) as image:
        return np.asarray(image.convert("RGB"), dtype=np.float32)


def encode_jpeg(rgb: np.ndarray) -> bytes:
    image = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), mode="RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return buffer.getvalue()


def luminance(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722


def calibration_tiles(tiles: list[tuple[int, int, int]]) -> list[tuple[int, int, int]]:
    if SMOKE_LIMIT > 0:
        return tiles[:SMOKE_LIMIT]
    if len(tiles) <= CALIBRATION_TILE_COUNT:
        return tiles
    stride = max(1, len(tiles) // CALIBRATION_TILE_COUNT)
    return tiles[::stride][:CALIBRATION_TILE_COUNT]


def sample_luminance(tile: bytes) -> np.ndarray:
    rgb = decode_rgb(tile)
    values = luminance(rgb).reshape(-1)
    step = max(1, values.size // 4096)
    return values[::step]


def calibrate_scene(scene: Scene, tiles: list[tuple[int, int, int]]) -> dict[str, float | int | bool]:
    samples: list[np.ndarray] = []
    selected = calibration_tiles(tiles)
    with ThreadPoolExecutor(max_workers=min(8, CONCURRENCY)) as pool:
        futures = [pool.submit(fetch_tile, scene, *tile) for tile in selected]
        for future in as_completed(futures):
            tile = future.result()
            if tile:
                samples.append(sample_luminance(tile))

    if not samples:
        return {"low": 4, "high": 244, "samples": 0, "fallback": True}

    values = np.concatenate(samples)
    if values.size < 1000:
        return {"low": 4, "high": 244, "samples": int(values.size), "fallback": True}

    return {
        "low": float(np.percentile(values, 1.5)),
        "high": float(np.percentile(values, 98.5)),
        "samples": int(values.size),
        "fallback": False,
    }


def blur_channel(channel: np.ndarray) -> np.ndarray:
    padded_x = np.pad(channel, ((0, 0), (1, 1)), mode="edge")
    tmp = padded_x[:, :-2] * 0.25 + padded_x[:, 1:-1] * 0.5 + padded_x[:, 2:] * 0.25
    padded_y = np.pad(tmp, ((1, 1), (0, 0)), mode="edge")
    return padded_y[:-2, :] * 0.25 + padded_y[1:-1, :] * 0.5 + padded_y[2:, :] * 0.25


def enhance_tile(tile: bytes, calibration: dict[str, float | int | bool]) -> bytes:
    rgb = decode_rgb(tile)
    low = float(calibration["low"])
    high = float(calibration["high"])
    scale = 255 / (high - low) if high > low + 18 else 1
    contrast = 1.04 if high > low + 18 else 1
    gamma = 0.96
    sharpen = 0.34
    saturation = 1.06

    blurred = np.stack([blur_channel(rgb[..., index]) for index in range(3)], axis=2)
    channels = rgb + (rgb - blurred) * sharpen
    adjusted_luma = luminance(channels)
    adjusted_luma = ((adjusted_luma - low) * scale - 127.5) * contrast + 127.5
    adjusted_luma = 255 * np.power(np.clip(adjusted_luma, 0, 255) / 255, gamma)

    original_luma = np.maximum(1, luminance(channels))
    scaled = channels * (adjusted_luma / original_luma)[..., None]
    scaled_luma = luminance(scaled)
    output = scaled_luma[..., None] + (scaled - scaled_luma[..., None]) * saturation
    return encode_jpeg(output)


def process_scene(scene: Scene, selected_tiles: list[tuple[int, int, int]], all_tiles: list[tuple[int, int, int]]) -> dict:
    calibration = calibrate_scene(scene, all_tiles)
    print(f"{scene.key} calibration: {calibration}", flush=True)
    written = 0
    skipped = 0
    errors = 0

    def worker(tile: tuple[int, int, int]) -> tuple[str, tuple[int, int, int], bytes | str | None]:
        zoom, x, y = tile
        try:
            raw = fetch_tile(scene, zoom, x, y)
            if not raw:
                return "skipped", tile, None
            return "written", tile, enhance_tile(raw, calibration)
        except Exception as exc:  # noqa: BLE001 - keep batch processing alive and report count.
            return "error", tile, repr(exc)

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = [pool.submit(worker, tile) for tile in selected_tiles]
        for index, future in enumerate(as_completed(futures), start=1):
            status, (zoom, x, y), payload = future.result()
            if status == "written" and isinstance(payload, bytes):
                output_path = OUTPUT_ROOT / scene.key / str(zoom) / str(x) / f"{y}.jpg"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(payload)
                written += 1
            elif status == "skipped":
                skipped += 1
            else:
                errors += 1
                print(f"{scene.key} error {zoom}/{x}/{y}: {payload}", flush=True)
            if index % 1000 == 0:
                print(f"{scene.key}: processed {index}/{len(selected_tiles)}", flush=True)

    print(
        f"{scene.key} complete: requested={len(selected_tiles)}, written={written}, skipped={skipped}, errors={errors}",
        flush=True,
    )
    return {
        "requested": len(selected_tiles),
        "written": written,
        "skipped": skipped,
        "errors": errors,
        "calibration": calibration,
    }


def scene_to_manifest(scene: Scene) -> dict:
    return {
        "label": scene.label,
        "cogUrl": scene.cog_url,
        "bounds": scene.bounds.__dict__,
        "gsdMeters": scene.gsd_meters,
    }


def create_archive() -> None:
    if ARCHIVE_PATH.exists():
        ARCHIVE_PATH.unlink()
    with tarfile.open(ARCHIVE_PATH, "w") as archive:
        archive.add(OUTPUT_ROOT, arcname="enhanced-satellite-tiles")
    size_mb = ARCHIVE_PATH.stat().st_size / 1024 / 1024
    print(f"archive: {ARCHIVE_PATH} ({size_mb:.1f} MB)", flush=True)


def upload_file(path: Path, path_in_repo: str, commit_message: str) -> None:
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
        commit_message=commit_message,
    )
    print(f"uploaded {path_in_repo}: {info}", flush=True)


def run_probe() -> None:
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise RuntimeError("HF_TOKEN missing from job environment")
    payload = {
        "status": "hf_cli_secret_upload_probe_ok",
        "identity": whoami(token=token).get("name"),
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    path = Path("/tmp/hf-cli-upload-probe.json")
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    upload_file(path, "probes/hf-cli-upload-probe.json", "Add HF CLI upload probe")
    print("UPLOAD_PROBE_OK", flush=True)


def run_full() -> None:
    if not ZOOM_LEVELS:
        raise RuntimeError("No valid ENHANCED_TILE_ZOOMS were provided")
    if ENHANCED_BOUNDS.west >= ENHANCED_BOUNDS.east or ENHANCED_BOUNDS.south >= ENHANCED_BOUNDS.north:
        raise RuntimeError("Enhanced imagery bounds do not intersect")

    if OUTPUT_ROOT.exists():
        for path in sorted(OUTPUT_ROOT.glob("**/*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    all_scene_tiles = {
        scene_key: [tile for zoom in ZOOM_LEVELS for tile in tiles_for_bounds(ENHANCED_BOUNDS, zoom)]
        for scene_key in SCENES
    }
    selected_scene_tiles = {
        scene_key: tiles[:SMOKE_LIMIT] if SMOKE_LIMIT > 0 else tiles
        for scene_key, tiles in all_scene_tiles.items()
    }

    started_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "generatedAt": started_at,
        "bounds": ENHANCED_BOUNDS.__dict__,
        "zoomLevels": ZOOM_LEVELS,
        "tilePixelSize": 512,
        "source": {scene_key: scene_to_manifest(scene) for scene_key, scene in SCENES.items()},
        "method": {
            "type": "deterministic-retina-enhancement",
            "generative": False,
            "operations": [
                "512px source tile fetch",
                "scene-sampled percentile luminance stretch",
                "mild unsharp mask",
                "mild saturation lift",
            ],
            "note": "No diffusion, GAN, or learned texture synthesis is used. Output is for visual inspection and preserves the raw Vantor COG fallback.",
        },
        "counts": {},
    }

    for scene_key, scene in SCENES.items():
        manifest["counts"][scene_key] = process_scene(
            scene, selected_scene_tiles[scene_key], all_scene_tiles[scene_key]
        )

    manifest_path = OUTPUT_ROOT / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    create_archive()
    upload_file(manifest_path, "manifest.json", "Add enhanced satellite tile manifest")
    upload_file(ARCHIVE_PATH, ARCHIVE_PATH.name, "Add enhanced satellite tile archive")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe-upload", action="store_true", help="only verify that the job can upload to the dataset")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.probe_upload:
        run_probe()
    else:
        run_full()


if __name__ == "__main__":
    main()
