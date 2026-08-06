# Market Odds Source Review

_Reviewed: June 14, 2026_

The market-assisted code is complete, but activation requires timestamped
pre-kickoff 1X2 prices whose storage and publication terms are auditable.

## Candidates

### Football-Data.co.uk

- Publishes free CSV/XLSX results and odds, including opening and closing
  prices for many domestic leagues.
- Its main historical catalogue is league-focused, so it does not provide the
  required broad overlap with the international-match training file.
- The site now links a World Cup XLSX resource, which may help with current
  tournament coverage.
- Its stated use boundary says data are provided for league-match prediction.
  Repository redistribution and publication of derived probabilities are not
  explicit enough for this project.

**Decision:** useful for coverage exploration, but do not check values into
the repository without written permission.

### The Odds API

- Provides current bookmaker odds and historical timestamp snapshots.
- Historical snapshots are available from June 6, 2020, at ten-minute
  intervals, and five-minute intervals from September 2022.
- Historical access is paid and costs usage credits per market and region.
- It cannot cover the full 2018-2019 selection period.

**Decision:** best documented option for current World Cup prices and a
2020-2026 experiment, subject to confirming subscription terms for storing
derived probabilities. It cannot alone satisfy the existing 2018-2025 gate.

### Kaggle and scraped odds collections

Dataset-specific licenses, timestamp provenance, bookmaker definitions, and
redistribution rights vary. A download being free does not make it suitable
for a public repository.

**Decision:** reject any dataset without explicit license, capture timestamp,
kickoff timestamp, and bookmaker-level provenance.

## Recommendation

1. Use a paid The Odds API account for a separately labeled 2020-2026
   experiment and current forecasts, after confirming storage terms.
2. Ask Football-Data.co.uk for written permission and precise World Cup
   coverage details.
3. Keep the market-assisted UI inactive until one source clears licensing,
   coverage, timestamp, and historical evaluation gates.

The evaluation baseline must be the calibrated production model
(`T=0.8857253661`), not the raw Dixon-Coles output.

## Sources

- https://www.football-data.co.uk/data.php
- https://the-odds-api.com/liveapi/guides/v4/
