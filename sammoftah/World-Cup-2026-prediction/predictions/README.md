# Pre-registered forecasts

Forecast files under this directory are immutable. The original
`YYYY-MM-DD/forecast.json` files are retained as historical evidence but are
not eligible for strict prospective scoring. New records live under
`predictions/live/`.

## Format

```json
{
  "forecast_date": "2026-06-13",
  "information_cutoff": "...",
  "generated_at": "...",
  "commit": "...",
  "model": "Elo-to-goals Dixon-Coles (fitted, see models/elo_fit_report.json)",
  "provenance": {
    "model_version": "...",
    "calibration_temperature": 0.8857253661047012,
    "team_ratings_sha256": "...",
    "snapshot_sha256": "..."
  },
  "ruleset_version": "ruleset_v1",
  "iterations": 3000,
  "fixtures": [...],
  "champion_probabilities": {...}
}
```

## Rules

1. Past forecast files must never be rewritten.
2. Each date directory must be created before its matchday begins.
3. The Track Record tab compares only eligible files against actual results.
4. A supported artifact requires normalized probabilities, a valid SHA-256
   manifest, complete model provenance, and
   `information_cutoff <= generated_at < kickoff_utc`.
5. Rejected and legacy artifacts remain visible in the evidence audit but
   cannot affect prospective metrics.

## Exact-Kickoff Live Proof

Each directory under `predictions/live/` contains one fixture forecast and a
separate `manifest.json` recording the SHA-256 digest of `forecast.json`.
New generation uses
`predictions/live/<fixture_id>/<generated_timestamp>/`, allowing multiple
immutable captures for the same fixture. The scanner remains recursive so the
original exact-kickoff proof layout remains readable.

Eligible captures are scored in mutually exclusive horizon cohorts based on
their generation time relative to kickoff:

- `final`: at most two hours before kickoff.
- `6h`: more than two and at most six hours.
- `24h`: more than six and at most 24 hours.
- `long_range`: more than 24 hours.

The Track Record also shows a latest-artifact compatibility summary. It does
not mix horizon cohorts when presenting the primary prospective evidence.

On June 14, the current production model was frozen for all 64 then-unplayed
group fixtures. The older Qatar-Switzerland proof remains untouched.
That dedicated proof is the only grandfathered legacy artifact; the old
date-batch files are classified as unsupported legacy evidence.
