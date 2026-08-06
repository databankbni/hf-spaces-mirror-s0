# World Cup 2026 Verification

_Updated: June 14, 2026_

## Snapshot

- Information cutoff: `2026-06-14T06:30:00Z`
- Teams: 48 across groups A-L
- Generated group fixtures: 72
- Recorded results: 8
- Snapshot validation: `validate_snapshot_integrity`

The checked-in snapshot records:

- Mexico 2-0 South Africa
- South Korea 2-1 Czechia
- Canada 1-1 Bosnia and Herzegovina
- United States 4-1 Paraguay
- Qatar 1-1 Switzerland
- Brazil 1-1 Morocco
- Haiti 0-1 Scotland
- Australia 2-0 Turkey

Results and cutoffs must be added with `scripts/update_snapshot.py`; historical
forecast files under `predictions/` must never be rewritten.

The audited automatic path is:

- `scripts/fetch_wc2026_results.py` reads football-data.org competition `WC`,
  season `2026`, stage `GROUP_STAGE` when a token is configured; otherwise it
  reads ESPN's public `fifa.world` scoreboard for the 2026 group stage.
- `data/world_cup_2026/provider_mappings/football_data.json` maps provider
  names to the repository’s canonical team names. Provider IDs discovered in
  a response are preserved in the candidate update for review.
- Competition, season, team mapping, fixture pair, kickoff tolerance, match
  status, and score shape must all validate.
- Corrections are labeled separately and require
  `scripts/update_snapshot.py --allow-corrections`.
- `.github/workflows/result-check.yml` opens or updates a PR; a human merge is
  required before the snapshot changes on `main`.

`FOOTBALL_DATA_API_KEY` is optional: football-data.org is primary when it is
configured, and ESPN is the keyless fallback. Every scheduled run reports the
provider used and whether it produced an audited update. Configure `HF_TOKEN`
with Space write access for exact revision deployment after merge.

All 72 group fixtures have UTC kickoff timestamps in
`data/world_cup_2026/kickoffs.json`. Run `make health` to verify schedule
coverage, snapshot integrity, and forecast manifests.
The health report also lists overdue unrecorded fixtures after a four-hour
provider grace period, artifact rejection counts, the latest result-update
provenance, and the repository Git revision.

## Bracket

Run:

```bash
PYTHONPATH=src python scripts/verify_world_cup_bracket.py
```

Verified scope:

- [x] Published Round-of-32 slots for matches 73-88.
- [x] Official Annex C assignment for every one of the 495 possible sets of
  eight qualifying third-place groups.
- [x] Round-of-16 pairings for matches 89-96.
- [x] Quarterfinal pairings for matches 97-100.
- [x] Semifinal pairings for matches 101-102.
- [x] Third-place pairing for match 103.
- [x] Final pairing for match 104.
- [x] No duplicate qualifier or same-group Round-of-32 pairing.

The machine-readable report is `results/bracket_verification.json`.

## Ranking Rules

Equal-point teams are ordered by head-to-head points, head-to-head goal
difference, head-to-head goals, overall goal difference, overall goals, fair
play, and FIFA ranking. The current snapshot has no card event feed, so fair
play defaults to zero and FIFA ranking is the deterministic final fallback.

## Sources

- https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/articles/fifa-world-cup-2026-match-schedule-fixtures-results-teams-stadiums
- https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_knockout_stage
- https://inside.fifa.com/fifa-world-ranking/men
- https://eloratings.net/World.tsv
- https://docs.football-data.org/general/v4/competition.html
