"""Shared helpers for Godena harvesters. No fakes: every agent must carry a
real, verifiable URL. Idempotent by slug. Snapshot is capped for the free Space."""
import json, os, re

SNAP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "agents_snapshot.json")
CAP = 12000  # max entries in the git-native index (a few MB; loads in memory, fast)

def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s[:80] or "agent"

def load():
    with open(SNAP, encoding="utf-8") as f:
        return json.load(f)

def save(snap):
    json.dump(snap, open(SNAP, "w", encoding="utf-8"), indent=0)

def merge(new, snap=None):
    """Add candidates (each a dict with a real website) deduped by slug, up to CAP."""
    if snap is None:
        snap = load()
    have = {a.get("slug") for a in snap}
    added = 0
    for a in new:
        if not a.get("website") or not a.get("slug"):
            continue
        if a["slug"] in have:
            continue
        if len(snap) >= CAP:
            break
        a.setdefault("tier", 1)
        a.setdefault("location", "global")
        a.setdefault("country", "global")
        a.setdefault("skill_primary", "coding")
        a.setdefault("skill_tags", ["ai"])
        a.setdefault("reputation_score", 8)
        snap.append(a)
        have.add(a["slug"])
        added += 1
    save(snap)
    # integrity
    slugs = [x["slug"] for x in snap]
    assert len(slugs) == len(set(slugs)), "duplicate slugs after merge"
    return added, len(snap)
