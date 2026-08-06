# Timestamped market odds

Market-assisted forecasts are optional and remain separate from the
independent model. No odds are bundled until their source and timestamps can
be audited.

`scripts/market_blend_evaluation.py` expects a CSV with:

```text
date,home_team,away_team,kickoff_utc,captured_at,horizon,home_odds,draw_odds,away_odds
```

- Odds are decimal 1X2 prices.
- `captured_at` and `kickoff_utc` must include a timezone.
- `captured_at` must be strictly before kickoff.
- `horizon` is either `opening` or `closing`; horizons are evaluated
  separately.
- Team identifiers must match `data/historical/matches.csv`.
- Source licensing and attribution must permit storing and publishing values.

The evaluation compares proportional, power, and Shin margin removal, fits
one market weight on 2018-2025, and confirms it on 2026 overall and neutral
matches. A paired bootstrap interval and minimum sample gates prevent a tiny
or noisy result from activating the market-assisted model. All three reported
paired intervals must remain below zero.

The independent baseline is the shipped temperature-calibrated forecast
(`T=0.8857253661047012`), not raw `T=1` output. Candidate source and licensing
research is recorded in `docs/market-data-source-review.md`.
