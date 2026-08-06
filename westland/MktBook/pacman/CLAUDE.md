# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Two independent Python applications live under `pacman/`:

1. **Lebanese Ms. Pac-Man** (`pacman/lebanese_pacman/game.py`) — A pygame-ce arcade game with Lebanese cultural theming (ghost names are Lebanese cities, food items are Lebanese cuisine, UI uses Lebanese flag colors).
2. **Johnson Distribution Explorer** (`pacman/prob.py`) — A Dash web dashboard for interactively visualizing Johnson statistical distributions (SU, SB, SL families).

## Dependencies & Running

### Lebanese Ms. Pac-Man
```
pip install -r pacman/lebanese_pacman/requirements.txt
python pacman/lebanese_pacman/game.py
```
Requires: `pygame-ce>=2.5.0`

### Johnson Distribution Explorer
```
pip install dash plotly scipy numpy
python pacman/prob.py
```
No requirements.txt exists for this app — dependencies are dash, plotly, scipy, numpy.

## Architecture

### game.py (~987 lines, single-file)
- **Constants & maze template** (top) — tile grid is 28x27, movement speeds, scoring, color palette, hardcoded maze layout
- **Enums & helpers** — Direction, GameMode (SCATTER/CHASE/FRIGHT/EATEN), State (TITLE/READY/PLAYING/DYING/GAMEOVER/LEVELUP), walkability checks, tunnel wrapping
- **Rendering functions** — `draw_pacman()`, `draw_ghost()`, `draw_cedar_tree()` for HUD
- **Ghost class** — Each ghost has unique chase AI targeting:
  - Byblos (red): targets player directly
  - Sidon (pink): targets 4 tiles ahead of player
  - Tyre (cyan): double vector from red ghost to 2-tiles-ahead
  - Baalbek (orange): chases if far, scatters if close
- **Game class** — Main loop (event → update → draw), state machine, collision detection, ghost release scheduling, mode cycling (scatter/chase phases)

### prob.py (~188 lines, single-file)
- Dash app with reactive callbacks
- `build_johnson()` parameterizes distributions via scipy.stats
- Sliders control gamma, delta, xi, lambda parameters; callback updates histogram, PDF, CDF, and stats summary in real time

## Notes

- Python 3.14 environment
- No test suite, linting config, or CI/CD exists
- Both apps are monolithic single-file designs
