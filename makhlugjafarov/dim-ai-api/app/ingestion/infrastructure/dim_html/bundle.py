"""Detect and enumerate an official DİM HTML e-textbook bundle.

A bundle is a directory containing a reader entry page (``basla.html`` or
``baslat.html`` — the name varies by template year) and a ``units/`` tree of
``pageN.xhtml`` files. The integer ``N`` in the filename is the book page number,
so the page→file map is exact (no OCR page-offset guessing).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_ENTRY_NAMES = ("basla.html", "baslat.html")
_PAGE_RE = re.compile(r"page(\d+)\.xhtml$", re.IGNORECASE)


@dataclass(frozen=True)
class BundlePage:
    """One book page: its printed page number and the XHTML file backing it."""

    page_number: int
    path: Path


class DimHtmlBundle:
    """A located DİM HTML e-textbook bundle.

    Construct via :meth:`detect` (returns ``None`` if the directory is not a
    recognizable bundle) so callers never hardcode the entry-file name.
    """

    def __init__(self, root: Path, entry: Path, pages: list[BundlePage]) -> None:
        self.root = root
        self.entry = entry
        self._pages = pages

    @classmethod
    def detect(cls, root: str | Path) -> "DimHtmlBundle | None":
        root = Path(root)
        if not root.is_dir():
            return None
        entry = next((root / name for name in _ENTRY_NAMES if (root / name).is_file()), None)
        units = root / "units"
        if entry is None or not units.is_dir():
            return None
        pages = cls._enumerate_pages(units)
        if not pages:
            return None
        return cls(root=root, entry=entry, pages=pages)

    @staticmethod
    def _enumerate_pages(units: Path) -> list[BundlePage]:
        found: dict[int, Path] = {}
        for path in units.rglob("*.xhtml"):
            match = _PAGE_RE.search(path.name)
            if match is None:
                continue
            number = int(match.group(1))
            # First occurrence wins; bundles keep one file per page number.
            found.setdefault(number, path)
        return [BundlePage(page_number=n, path=found[n]) for n in sorted(found)]

    @property
    def pages(self) -> list[BundlePage]:
        return list(self._pages)

    @property
    def page_count(self) -> int:
        return len(self._pages)

    def title(self) -> str | None:
        """Best-effort book title from the entry page's ``<title>`` tag."""
        try:
            text = self.entry.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None
        match = re.search(r"<title>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
        return match.group(1).strip() if match else None
