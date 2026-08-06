# Summary

The bundle checks three selected claims from `iPjuUQbkfl` using a deterministic CPU implementation of the paper's linear Gaussian/RMT setting.

- Silverstein self-consistency gives `kappa(sigma^2) > sigma^2`, which increases lower-band denoiser shrinkage.
- The Result 4.2 variance formula peaks near eigenmodes with variance close to `kappa` and decreases with larger dataset size.
- Empirical split sampling maps built from covariance square roots overshrink low modes and show positive same-seed cross-split disagreement that decreases with larger `n`.

The evidence is toy-scale relative to the paper's deep UNet/DiT experiments.
