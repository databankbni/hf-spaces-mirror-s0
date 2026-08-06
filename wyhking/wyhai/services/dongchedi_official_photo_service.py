from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from datetime import datetime, timedelta, timezone
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PHOTO_DIR = ROOT / "data/external/dongchedi_official_photos/current"

SERIES_PHOTO_ALIASES = {
    "eπ007": "奕派007",
    "东风奕派eπ007": "奕派007",
    "eπ008": "奕派008",
    "东风奕派eπ008": "奕派008",
    "星纪元es": "星途ES",
    "星途星纪元es": "星途ES",
    "极狐t1": "极狐 贝塔T1",
    "arcfox极狐t1": "极狐 贝塔T1",
}

_DCD_IMAGE_KEY_PATTERN = re.compile(
    r"https?://p\d+-dcd\.byteimg\.com/(?P<bucket>tos-cn-i-dcdx|motor-mis-img)/"
    r"(?P<key>[0-9a-fA-F]{24,})~"
)


def _norm(value: Any) -> str:
    return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")


def _count_csv_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("rb") as handle:
        return max(0, sum(1 for _ in handle) - 1)


def _stable_photo_url(value: Any) -> str:
    """Rewrite expired/invalid ImageX templates to the stable ranking cover."""
    url = str(value or "").strip()
    if not url:
        return ""
    match = _DCD_IMAGE_KEY_PATTERN.search(url)
    if not match:
        return url
    return (
        f"https://p9-dcd.byteimg.com/{match.group('bucket')}/{match.group('key')}"
        "~tplv-resize:640:0.png?psm=motor.rank.data"
    )


class DongchediOfficialPhotoService:
    def __init__(self, photo_dir: str | Path | None = None) -> None:
        self.photo_dir = Path(photo_dir) if photo_dir else DEFAULT_PHOTO_DIR
        self.series_index_path = self.photo_dir / "official_series_photo_index.csv"
        self.car_index_path = self.photo_dir / "official_car_photo_index.csv"
        self.records_path = self.photo_dir / "official_photo_records.csv"
        self._series_rows: list[dict[str, Any]] | None = None
        self._series_by_key: dict[str, dict[str, Any]] | None = None

    @property
    def available(self) -> bool:
        return self.series_index_path.exists() or self.car_index_path.exists()

    @property
    def series_rows(self) -> list[dict[str, Any]]:
        if self._series_rows is None:
            self._series_rows = self._load_series_rows()
        return self._series_rows

    @property
    def series_by_key(self) -> dict[str, dict[str, Any]]:
        if self._series_by_key is None:
            index: dict[str, dict[str, Any]] = {}
            for row in self.series_rows:
                series_key = _norm(row.get("series_name"))
                brand_series_key = _norm(f"{row.get('brand_name')}{row.get('series_name')}")
                if series_key and series_key not in index:
                    index[series_key] = row
                if brand_series_key and brand_series_key not in index:
                    index[brand_series_key] = row
            self._series_by_key = index
        return self._series_by_key

    def _load_series_rows(self) -> list[dict[str, Any]]:
        if not self.series_index_path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self.series_index_path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                image_url = str(row.get("cover_image_url") or "").strip()
                if not image_url:
                    continue
                rows.append(row)
        return rows

    def find_series_photo(self, brand: Any = "", series: Any = "") -> dict[str, Any] | None:
        brand_text = str(brand or "").strip()
        series_text = str(series or "").strip()
        if not series_text:
            return None
        alias = SERIES_PHOTO_ALIASES.get(_norm(series_text)) or SERIES_PHOTO_ALIASES.get(
            _norm(f"{brand_text}{series_text}")
        )
        if alias:
            series_text = alias
        keys = [_norm(f"{brand_text}{series_text}"), _norm(series_text)]
        row = next((self.series_by_key.get(key) for key in keys if key in self.series_by_key), None)
        if not row:
            target = _norm(series_text)
            row = next((item for item in self.series_rows if target and target in _norm(item.get("series_name"))), None)
        if not row:
            return None
        image_url = _stable_photo_url(row.get("cover_image_url"))
        return {
            "brand_name": row.get("brand_name"),
            "series_name": row.get("series_name"),
            "series_id": row.get("series_id"),
            "image_url": image_url,
            "proxied_image_url": f"/api/vehicle/photo-proxy?url={quote(str(image_url), safe='')}" if image_url else "",
            "local_path": row.get("local_cover_path") or "",
            "image_count": _safe_int(row.get("image_count")),
            "validated_image_count": _safe_int(row.get("validated_image_count")),
            "source": "dongchedi_official_photo_index",
            "updated_at": row.get("updated_at"),
        }

    def summary(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "series_photo_count": _count_csv_rows(self.series_index_path),
            "car_photo_count": _count_csv_rows(self.car_index_path),
            "photo_record_count": _count_csv_rows(self.records_path),
            "source_dir": str(self.photo_dir),
            "updated_at": _latest_mtime(self.series_index_path, self.car_index_path, self.records_path),
        }


def _safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def _latest_mtime(*paths: Path) -> str:
    existing = [path for path in paths if path.exists()]
    if not existing:
        return ""
    latest = max(existing, key=lambda path: path.stat().st_mtime)
    return datetime.fromtimestamp(latest.stat().st_mtime, timezone(timedelta(hours=8))).isoformat()


@lru_cache(maxsize=2)
def get_dongchedi_official_photo_service(photo_dir: str = "") -> DongchediOfficialPhotoService:
    return DongchediOfficialPhotoService(photo_dir or None)
