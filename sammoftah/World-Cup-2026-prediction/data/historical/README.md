# Historical match dataset

`matches.csv` is built by `scripts/build_historical_dataset.py` from
[eloratings.net](https://www.eloratings.net)'s per-year results files
(`https://www.eloratings.net/<year>_results.tsv`) — the same source already
cited in `data/world_cup_2026/snapshot.json["sources"]`.

- **Range**: 2015-01-03 to 2026-06-12 (built 2026-06-13).
- **Size**: 11,094 international matches (raw `data/historical/raw/*.tsv`
  caches one file per year).
- **Columns**: `date, home_team, away_team, home_goals, away_goals,
  home_elo, away_elo, neutral, tournament`. `home_elo`/`away_elo` are each
  team's Elo rating *going into* that match, as computed by eloratings.net
  — no separate historical-Elo lookup or static-current-Elo approximation
  was needed. Team codes are eloratings.net's (mostly ISO 3166-1 alpha-2,
  with exceptions such as `EN`=England, `SQ`=Scotland, `BA`=Bosnia and
  Herzegovina).
- **`neutral`**: `True` when the match was played in a third country (the
  `host` field in the source is set and differs from `home_team`), `False`
  when the listed home team played on its own soil.
- **Exclusions**: 12 matches that appear in `data/raw/challenge_matches.json`
  (the LLM-extraction challenge set) and fall within 2015-2026 are removed
  — see `CHALLENGE_MATCH_EXCLUSIONS` in the build script. The challenge set
  must never be used for fitting or evaluating the forecasting model.
- **2026 World Cup matches**: the dataset includes the 4 group matches
  played so far (through 2026-06-12, matching
  `data/world_cup_2026/snapshot.json`). Fitting and backtesting scripts
  must respect `information_cutoff` and not train on matches after it
  relative to whatever cutoff a given forecast claims.

This is a real-but-smaller dataset relative to the ~2,000-5,000 match
target in the original remediation plan (11k matches across 12 years is
on the larger side, but only carries 9 columns per match and no team
metadata beyond Elo). Re-run
Install the modeling dependencies with `pip install -e '.[modeling]'`, then
run `python scripts/build_historical_dataset.py --start-year <Y>
--end-year <Y>` to refresh or extend the range.
