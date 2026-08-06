"""Player profile photos for the award-shortlist player cards.

Photo URLs come from a one-time snapshot of Wikipedia/Wikimedia Commons
thumbnails, cached in `data/world_cup_2026/player_images.json` (see
`comparison.py` for the same caching pattern). Nothing is fetched at
runtime, so the app has no extra network dependency and keeps working if
a player's photo is missing.
"""

from __future__ import annotations

import html
import json
from functools import lru_cache
from pathlib import Path

from underdog_lab.config import DATA_DIR

PLAYER_IMAGES_PATH = DATA_DIR / "world_cup_2026" / "player_images.json"


@lru_cache(maxsize=1)
def load_player_images() -> dict[str, dict]:
    if not PLAYER_IMAGES_PATH.exists():
        return {}
    return json.loads(PLAYER_IMAGES_PATH.read_text(encoding="utf-8")).get("players", {})


def player_photo_url(name: str) -> str:
    """Return a cached thumbnail URL for ``name``, or '' if none is known."""
    return load_player_images().get(name, {}).get("thumbnail", "")


def player_photo_html(name: str) -> str:
    """An `<img>` for the player's photo, or an initials avatar if unknown."""
    url = player_photo_url(name)
    if url:
        return (
            f'<img class="player-photo" src="{html.escape(url)}" '
            f'alt="{html.escape(name)}" loading="lazy" referrerpolicy="no-referrer">'
        )
    initials = "".join(part[0] for part in name.split() if part)[:2].upper()
    return f'<div class="player-photo player-photo-fallback">{html.escape(initials)}</div>'
