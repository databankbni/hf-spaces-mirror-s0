# Elo rating corrections (2026-06-13)

`teams.json` lists each team's Elo rating from `eloratings.net/World.tsv`
(cited in `snapshot.json["sources"]`). A full diff of all 48 teams against
`World.tsv` as of 2026-06-13 found 4 teams off the source values, all in
the two host groups (B and D):

| Team                     | teams.json (old) | World.tsv (correct) |
|--------------------------|------------------:|---------------------:|
| United States            | 1726              | 1780                 |
| Paraguay                  | 1834              | 1780                 |
| Canada                    | 1788              | 1767                 |
| Bosnia and Herzegovina    | 1595              | 1616                 |

The United States/Paraguay error was large enough to invert the matchup:
`teams.json` had Paraguay (rank 39) rated above the United States (rank 14)
by 108 points, when `World.tsv` puts the United States above Paraguay by
0 points (both 1780 — a true pick'em). This directly fed the 2026-06-13
forecast for WC26-019 (USA vs Paraguay), which gave Paraguay the higher
win probability; the actual result was USA 4-1 Paraguay.

The other 44 teams matched `World.tsv` exactly (diff = 0) and were left
unchanged.

`World.tsv` codes use mostly-ISO-3166-1-alpha-2 country codes, with a few
non-obvious ones relevant here: `US` = United States, `PY` = Paraguay,
`CA` = Canada, `BA` = Bosnia and Herzegovina, `ZA` = South Africa,
`SQ` = Scotland, `EN` = England.
