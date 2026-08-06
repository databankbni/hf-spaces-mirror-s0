import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from underdog_lab.ui.app import LIGHT_THEME, demo
from underdog_lab.ui.theme import CSS


if __name__ == "__main__":
    demo.launch(css=CSS, theme=LIGHT_THEME)
