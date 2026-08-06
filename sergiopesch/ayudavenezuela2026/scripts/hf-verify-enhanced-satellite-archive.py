# /// script
# dependencies = ["huggingface-hub", "numpy", "Pillow"]
# ///

"""Verify the enhanced satellite tile archive inside Hugging Face Jobs."""

from __future__ import annotations

import io
import json
import os
import tarfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from huggingface_hub import HfApi, hf_hub_download
from PIL import Image, ImageDraw


REPO_ID = os.environ.get("OUTPUT_REPO", "sergiopesch/ayudavenezuela2026-enhanced-satellite-tiles")
ARCHIVE_NAME = os.environ.get(
    "ENHANCED_TILE_ARCHIVE_NAME", "ayudavenezuela2026-enhanced-satellite-tiles-z18-z19-20260702.tar"
)
REPORT_PATH = Path("/tmp/enhanced-satellite-verification-report.json")
CONTACT_SHEET_PATH = Path("/tmp/enhanced-satellite-sample-contact-sheet.jpg")


def decode_tile(tar: tarfile.TarFile, member: tarfile.TarInfo) -> Image.Image:
    handle = tar.extractfile(member)
    if handle is None:
        raise RuntimeError(f"Cannot read {member.name}")
    data = handle.read()
    image = Image.open(io.BytesIO(data)).convert("RGB")
    image.load()
    return image


def image_stats(image: Image.Image) -> dict:
    values = np.asarray(image, dtype=np.float32)
    luma = values[..., 0] * 0.2126 + values[..., 1] * 0.7152 + values[..., 2] * 0.0722
    gy, gx = np.gradient(luma)
    return {
        "width": image.width,
        "height": image.height,
        "meanLuminance": round(float(luma.mean()), 3),
        "stddevLuminance": round(float(luma.std()), 3),
        "meanGradient": round(float(np.sqrt(gx * gx + gy * gy).mean()), 3),
    }


def pick_samples(members: list[tarfile.TarInfo], limit: int = 8) -> list[tarfile.TarInfo]:
    if len(members) <= limit:
        return members
    indexes = np.linspace(0, len(members) - 1, limit, dtype=int)
    return [members[int(index)] for index in indexes]


def build_contact_sheet(samples: list[tuple[str, Image.Image]]) -> None:
    tile_size = 180
    label_height = 28
    columns = 4
    rows = (len(samples) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * tile_size, rows * (tile_size + label_height)), "white")
    draw = ImageDraw.Draw(sheet)
    for index, (label, image) in enumerate(samples):
        x = (index % columns) * tile_size
        y = (index // columns) * (tile_size + label_height)
        sheet.paste(image.resize((tile_size, tile_size)), (x, y))
        draw.text((x + 4, y + tile_size + 6), label[-34:], fill=(0, 0, 0))
    sheet.save(CONTACT_SHEET_PATH, format="JPEG", quality=88)


def main() -> None:
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise RuntimeError("HF_TOKEN missing from job environment")

    archive_path = Path(
        hf_hub_download(
            repo_id=REPO_ID,
            filename=ARCHIVE_NAME,
            repo_type="dataset",
            token=token,
            local_dir="/tmp/enhanced-satellite-verify-download",
        )
    )
    manifest_path = Path(
        hf_hub_download(
            repo_id=REPO_ID,
            filename="manifest.json",
            repo_type="dataset",
            token=token,
            local_dir="/tmp/enhanced-satellite-verify-download",
        )
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    with tarfile.open(archive_path, "r") as tar:
        members = [member for member in tar.getmembers() if member.isfile()]
        jpg_members = [member for member in members if member.name.endswith(".jpg")]
        before_members = sorted((member for member in jpg_members if "/before/" in member.name), key=lambda member: member.name)
        after_members = sorted((member for member in jpg_members if "/after/" in member.name), key=lambda member: member.name)
        manifest_members = [member for member in members if member.name.endswith("/manifest.json")]

        expected = {
            "before": manifest["counts"]["before"]["written"],
            "after": manifest["counts"]["after"]["written"],
        }
        actual = {"before": len(before_members), "after": len(after_members)}

        invalid: list[dict] = []
        checked = 0
        for member in jpg_members:
            try:
                image = decode_tile(tar, member)
                if image.size != (512, 512):
                    invalid.append({"path": member.name, "reason": f"unexpected size {image.size}"})
            except Exception as exc:  # noqa: BLE001 - report corrupt files without hiding path.
                invalid.append({"path": member.name, "reason": repr(exc)})
            checked += 1
            if checked % 5000 == 0:
                print(f"checked {checked}/{len(jpg_members)} JPEGs", flush=True)

        samples: list[tuple[str, Image.Image]] = []
        sample_stats: dict[str, list[dict]] = {"before": [], "after": []}
        for scene_key, scene_members in (("before", before_members), ("after", after_members)):
            for member in pick_samples(scene_members, 8):
                image = decode_tile(tar, member)
                stats = image_stats(image)
                stats["path"] = member.name
                sample_stats[scene_key].append(stats)
                samples.append((member.name, image))

    build_contact_sheet(samples)

    report = {
        "verifiedAt": datetime.now(timezone.utc).isoformat(),
        "repoId": REPO_ID,
        "archiveName": ARCHIVE_NAME,
        "archiveSizeBytes": archive_path.stat().st_size,
        "manifestGeneratedAt": manifest.get("generatedAt"),
        "bounds": manifest.get("bounds"),
        "zoomLevels": manifest.get("zoomLevels"),
        "tilePixelSize": manifest.get("tilePixelSize"),
        "method": manifest.get("method"),
        "counts": {
            "expected": expected,
            "actual": actual,
            "match": expected == actual,
            "jpgChecked": checked,
            "invalidCount": len(invalid),
            "invalid": invalid[:50],
            "tarManifestFiles": len(manifest_members),
        },
        "sampleStats": sample_stats,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    api = HfApi(token=token)
    api.upload_file(
        path_or_fileobj=str(REPORT_PATH),
        path_in_repo="verification/enhanced-satellite-verification-report-20260702.json",
        repo_id=REPO_ID,
        repo_type="dataset",
        token=token,
        commit_message="Add enhanced satellite archive verification report",
    )
    api.upload_file(
        path_or_fileobj=str(CONTACT_SHEET_PATH),
        path_in_repo="verification/enhanced-satellite-sample-contact-sheet-20260702.jpg",
        repo_id=REPO_ID,
        repo_type="dataset",
        token=token,
        commit_message="Add enhanced satellite sample contact sheet",
    )
    print(json.dumps(report["counts"], sort_keys=True), flush=True)
    print("VERIFY_OK", flush=True)


if __name__ == "__main__":
    main()
