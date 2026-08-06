"""Parse each XHTML page into heading candidates + body text (signal-driven).

The whole point of the HTML road is that the text is clean and the visual
hierarchy is *consistent within a book*. We therefore extract, per short styled
line, a set of **signals** — font-size (from any ``fsNN`` class on the element or
its ancestors), a leading lesson number (``"23. ..."``), ALL-CAPS, boldness,
centering — and leave the ranking of those signals into tree depth to
:mod:`tree`. We never branch on specific class names (``text-darkred`` etc.):
those differ between the 2014 and 2019 templates and even rotate within one book.
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass

from bs4 import BeautifulSoup
from bs4 import XMLParsedAsHTMLWarning

from app.ingestion.infrastructure.dim_html.bundle import BundlePage

# These are XHTML files; the lenient HTML parser handles minor malformedness more
# robustly than the strict XML parser, so silence the (expected) advisory.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

_FS_RE = re.compile(r"\bfs(\d+)\b")
_LEADING_NUM_RE = re.compile(r"^\s*(\d{1,3})[.)]\s+\S")
_WS_RE = re.compile(r"\s+")

# A short styled line is only treated as a heading by font size if the size is at
# least this large; smaller fsNN classes (fs14/fs20) are body/caption text.
_HEADING_FONT_MIN = 24
# Heading lines are short; longer styled lines are pull-quotes / keyword rows.
_MAX_HEADING_CHARS = 80
_MIN_HEADING_CHARS = 3
# Below this much body text, a page is image-only (its content lives in a JPEG).
_IMAGE_ONLY_TEXT_MAX = 15


@dataclass(frozen=True)
class HeadingCandidate:
    text: str
    page: int
    reading_order: int
    font_size: int | None
    is_bold: bool
    is_caps: bool
    leading_number: int | None
    centered: bool
    colored: bool

    @property
    def signature(self) -> tuple[int, int, int, int]:
        """Rank key for grouping into depth levels (higher tuple = shallower).

        Font size dominates (a bigger heading is always a higher level); a leading
        lesson number, then ALL-CAPS, then boldness break ties at equal size. This
        ordering is what lets one rule serve both books: history ranks by font
        size (48 > 28 > 24), biology ranks numbered fs24 lessons above unnumbered
        styled lines.
        """
        return (
            self.font_size or 0,
            1 if self.leading_number is not None else 0,
            1 if self.is_caps else 0,
            1 if self.is_bold else 0,
        )


@dataclass(frozen=True)
class PageExtract:
    page_number: int
    text_length: int
    is_image_only: bool
    headings: list[HeadingCandidate]


def _font_size(classes: list[str]) -> int | None:
    for token in classes:
        match = _FS_RE.search(token)
        if match:
            return int(match.group(1))
    return None


def _caps_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    upper = sum(1 for c in letters if c == c.upper() and c != c.lower())
    return upper / len(letters)


def _ancestor_font_size(element) -> int | None:
    node = element
    while node is not None and getattr(node, "get", None) is not None:
        size = _font_size(node.get("class", []) or [])
        if size is not None:
            return size
        node = node.parent
    return None


def _is_bold(element) -> bool:
    node = element
    depth = 0
    while node is not None and getattr(node, "name", None) is not None and depth < 4:
        if node.name in ("b", "strong"):
            return True
        classes = node.get("class", []) or []
        if any("bold" in c for c in classes):
            return True
        node = node.parent
        depth += 1
    return False


def _is_centered(element) -> bool:
    node = element
    depth = 0
    while node is not None and getattr(node, "name", None) is not None and depth < 4:
        classes = node.get("class", []) or []
        if any("center" in c for c in classes):
            return True
        node = node.parent
        depth += 1
    return False


def _is_colored(classes: list[str]) -> bool:
    # Any explicit text-colour class is a styling signal (value-agnostic).
    return any(("text-" in c and "text-center" not in c) for c in classes)


def _direct_text(element) -> str:
    parts = element.find_all(string=True, recursive=False)
    return _WS_RE.sub(" ", "".join(parts)).strip()


def _looks_like_heading(
    *,
    font_size: int | None,
    is_caps: bool,
    number: int | None,
    is_bold: bool,
    colored: bool,
) -> bool:
    """A short line is a heading only with a real heading signal.

    A leading lesson number is decisive only with *curriculum* styling — a colour
    class or a heading-sized font. Bold alone is not enough: in-lesson enumerations
    ("2. Prosesləri…") are bold but uncoloured, while real lesson titles carry the
    template's coloured heading class. A heading-sized font is decisive on its own.
    ALL-CAPS alone is NOT enough — diagrams and comparison tables are full of bare
    caps words (BUXAREST, VERDEN, SİYASİ); caps only counts when it also carries
    styling (bold or a colour class), which body/diagram text lacks.
    """
    heading_font = font_size is not None and font_size >= _HEADING_FONT_MIN
    if number is not None and (colored or heading_font):
        return True
    if heading_font:
        return True
    if is_caps and (is_bold or colored):
        return True
    return False


def extract_page(page: BundlePage) -> PageExtract:
    raw = page.path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(raw, "lxml")
    head = soup.find("head")
    if head is not None:
        head.decompose()

    body_text = _WS_RE.sub(" ", soup.get_text(" ")).strip()
    is_image_only = len(body_text) < _IMAGE_ONLY_TEXT_MAX

    headings: list[HeadingCandidate] = []
    seen: set[str] = set()
    order = 0
    for element in soup.find_all(True):
        text = _direct_text(element)
        if not (_MIN_HEADING_CHARS <= len(text) <= _MAX_HEADING_CHARS):
            continue
        if not any(c.isalpha() for c in text):  # drop pure numbers / punctuation ("9")
            continue
        classes = element.get("class", []) or []
        font_size = _font_size(classes) or _ancestor_font_size(element)
        number_match = _LEADING_NUM_RE.match(text)
        number = int(number_match.group(1)) if number_match else None
        is_caps = _caps_ratio(text) > 0.8
        is_bold = _is_bold(element)
        colored = _is_colored(classes)

        if not _looks_like_heading(
            font_size=font_size, is_caps=is_caps, number=number, is_bold=is_bold, colored=colored
        ):
            continue
        if text in seen:  # a heading wrapped in nested tags appears once
            continue
        seen.add(text)
        order += 1
        headings.append(
            HeadingCandidate(
                text=text,
                page=page.page_number,
                reading_order=order,
                font_size=font_size,
                is_bold=is_bold,
                is_caps=is_caps,
                leading_number=number,
                centered=_is_centered(element),
                colored=colored,
            )
        )

    return PageExtract(
        page_number=page.page_number,
        text_length=len(body_text),
        is_image_only=is_image_only,
        headings=headings,
    )


def extract_pages(pages: list[BundlePage]) -> list[PageExtract]:
    return [extract_page(p) for p in pages]
