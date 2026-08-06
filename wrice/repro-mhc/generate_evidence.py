#!/usr/bin/env python3
"""Run the mHC evidence CLI without installing editable source metadata."""

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from mhc_repro.cli import main


if __name__ == "__main__":
    main()
