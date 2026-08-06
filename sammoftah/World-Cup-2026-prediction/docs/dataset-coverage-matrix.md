## Training Dataset Coverage Matrix

Total examples: **861**

### Factor Type × Team Attribution

| Factor Type | Home | Away | Both | Unknown | Total |
|---:|---:|---:|---:|---:|---:|
| key_attacker_unavailable | 53 | 36 | 0 | 0 | **89** |
| key_defender_unavailable | 42 | 58 | 0 | 0 | **100** |
| goalkeeper_unavailable | 35 | 42 | 0 | 0 | **77** |
| multiple_starters_unavailable | 32 | 35 | 0 | 0 | **67** |
| squad_rotation | 37 | 33 | 0 | 0 | **70** |
| fatigue_disadvantage | 39 | 48 | 0 | 0 | **87** |
| rest_advantage | 44 | 30 | 0 | 0 | **74** |
| travel_disadvantage | 49 | 38 | 0 | 0 | **87** |
| altitude_disadvantage | 34 | 42 | 0 | 0 | **76** |
| heat_disadvantage | 40 | 37 | 0 | 0 | **77** |
| home_advantage | 34 | 36 | 0 | 0 | **70** |
| neutral_venue | 0 | 0 | 51 | 0 | **51** |
| defensive_game_state | 0 | 8 | 51 | 0 | **59** |
| must_win_incentive | 52 | 42 | 0 | 0 | **94** |

### Structural Coverage

| Category | Count |
|---:|---:|
| One-factor examples | 309 |
| Multi-factor examples | 354 |
| No-factor examples | 198 |
| Negation | 41 |
| Contradiction | 14 |
| Unsupported claims | 182 |
| Pronoun/role references | 130 |
| Ambiguous attribution | 16 |
| Prompt injection | 24 |
| Same factor both teams | 37 |
| Different factors both teams | 41 |

### Data Quality

| Metric | Value |
|---:|---:|
| Unique normalized texts | 861 |
| Total factor occurrences | 1078 |
| Review status | All pending (synthetic) |
| Provenance | compositional synthetic + gap-fill; human review required |
| Challenge-match contamination | None (synthetic team pairs only) |

