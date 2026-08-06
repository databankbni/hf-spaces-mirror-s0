"""Weighted random pair selection for autonomous bot conversations."""
from __future__ import annotations

import random
from itertools import combinations

from mktbook.db import queries
from mktbook.db.models import Bot


async def select_pair(active_bots: list[Bot]) -> tuple[Bot, Bot] | None:
    """Pick a pair of bots, favoring pairs that have talked least."""
    if len(active_bots) < 2:
        return None

    pair_counts = await queries.get_pair_counts()
    all_pairs = list(combinations(active_bots, 2))

    if not all_pairs:
        return None

    # Weight = 1 / (1 + conversation_count) — least-recent pairs get higher weight
    weights: list[float] = []
    for a, b in all_pairs:
        key = (min(a.id, b.id), max(a.id, b.id))
        count = pair_counts.get(key, 0)
        weights.append(1.0 / (1.0 + count))

    chosen = random.choices(all_pairs, weights=weights, k=1)[0]
    # Randomly pick who initiates
    if random.random() < 0.5:
        return chosen[0], chosen[1]
    return chosen[1], chosen[0]
