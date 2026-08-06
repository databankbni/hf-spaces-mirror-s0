# Integrity notes (added 2026-06-13)

Per `predictions/README.md` rule 1, the `forecast.json` files under
`predictions/2026-06-13/` through `predictions/2026-06-27/` are immutable
and have not been edited or regenerated. This note documents a
pre-registration integrity issue found in those files so future readers
do not mistake them for clean baselines.

## What happened

All 15 directories were generated in a single batch on 2026-06-13 between
00:53:58 and 01:03:24 UTC, each containing the same 70 "upcoming" fixtures
(`data/world_cup_2026/snapshot.json` had only 2 results recorded at that
time: Mexico 2-0 South Africa and South Korea 2-1 Czechia, both from
2026-06-11).

By the time these files were generated, two more group-stage matches had
already been played in the real world on 2026-06-12:

- **WC26-007 Canada vs Bosnia and Herzegovina: 1-1**
  (https://www.espn.com/soccer/match/_/gameId/760416/bosnia-herzegovina-canada)
- **WC26-019 United States vs Paraguay: 4-1**
  (https://www.espn.com/soccer/match/_/gameId/760417/paraguay-united-states)

Both are listed as "upcoming" fixtures with forecast probabilities in
every one of the 15 files above. Per `predictions/README.md` rule 4
("A forecast generated after any result in its window is not a
pre-registered forecast"), the forecasts for WC26-007 and WC26-019 in
these files are **not** pre-registered and should not be scored as such
in the Track Record tab.

## A second, compounding issue

The `information_cutoff` field is also internally inconsistent across the
batch: the 2026-06-13 directory used `2026-06-12T19:45:00Z`, while every
other directory (2026-06-14 through 2026-06-27, generated 9 minutes later)
used `2026-06-14T18:00:00Z` — a cutoff that was *in the future* relative to
its own `generated_at` timestamp. A future-dated cutoff is exactly what let
already-decided matches (WC26-007, WC26-019) slip through as "upcoming."

## Fix applied going forward

- `data/world_cup_2026/snapshot.json` now records both results above and
  sets `information_cutoff` to `2026-06-13T04:30:00Z`, after the June 12
  local-date matches completed in North America but before the June 13
  matchday.
- `src/underdog_lab/world_cup/integrity.py` adds
  `validate_snapshot_integrity()`, called from
  `scripts/generate_forecast.py` before any forecast is written. It
  refuses to generate a forecast if `information_cutoff` is in the future,
  or if any fixture on or before `information_cutoff` is missing a result.
  This makes the failure mode in this note impossible to reproduce
  silently.
- The Track Record now selects at most one eligible forecast per fixture,
  rejects files with future cutoffs, and conservatively rejects forecasts
  generated on the fixture's calendar date because exact kickoff timestamps
  are not stored.

The 15 existing files are left untouched per rule 1. Any scoring of the
Track Record tab against these files should exclude WC26-007 and WC26-019
from the pre-registration accuracy calculation, or flag them as
contaminated.
