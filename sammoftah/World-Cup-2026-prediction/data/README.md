# Data

`raw/challenge_matches.json` contains a curated historical challenge set.
The displayed pre-match Elo values are approximate research inputs and are
not represented as official ratings.

Run:

```bash
PYTHONPATH=src python scripts/prepare_matches.py
```

This derives `lambda_home` and `lambda_away` from the pre-match Elo
difference. The match outcome is not used to derive the rates. The checked-in
bootstrap coefficients are transparent defaults; a later research release
should fit them on a separately licensed historical training set while
excluding all challenge matches.

The challenge set is for product demonstration, not evidence that the model
is state of the art.
