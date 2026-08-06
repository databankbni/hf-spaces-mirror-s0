#!/usr/bin/env python3
"""
RBC Software Master Extractor

One dynamic extractor for RBC Weekly Software and Monthly Software PDFs.

The script extracts the same deliverable workbook used by the legacy weekly and
monthly scripts, but it does not rely on fixed page numbers or hardcoded row
positions. It discovers sections by title, reads table headers from PDF
coordinates, builds column bands dynamically, and writes a consistent workbook.

Output sheets
------------
1. Symbol Rating and PT
2. Sales and EPS (Bold Only)
3. Only Revenue
4. Metadata Reference
Optional: Extraction Audit

Example
-------
python RBC_Software_Master_Extractor.py --pdf "Weekly Software.pdf" --output "WeeklySoftware_Extract.xlsx"
python RBC_Software_Master_Extractor.py --pdf "Monthly Software.pdf" --output "MonthlySoftware_Extract.xlsx" --audit-sheet
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import fitz  # PyMuPDF
import pandas as pd


# -----------------------------------------------------------------------------
# Business constants
# -----------------------------------------------------------------------------

BAD_TICKERS = {
    "TABLE", "MONTHLY", "WEEKLY", "SOFTWARE", "SOURCE", "RATING",
    "TICKER", "PRICE", "EV", "NAME", "RETURN", "RETURNS", "STOCK",
    "NON-GAAP", "GAAP", "MEAN", "MEDIAN", "AVERAGE", "AVG", "FACTSET",
    "RBC", "CAPITAL", "MARKETS", "SUMMARY", "COVERAGE", "UNIVERSE",
}

# RBC tables include a few genuine one-letter tickers. Other one-letter tokens
# are usually extraction fragments and are rejected.
ALLOWED_SINGLE_LETTER_TICKERS = {"S", "U"}

RATING_VALUES = {"OP", "SP", "UP", "R"}
YEAR_RE = re.compile(r"^CY/\d{2}[AE]?$", re.I)
DATE_RE = re.compile(r"^(?:\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}-\d{1,2}-\d{2,4})$")
NUMERIC_TOKEN_RE = re.compile(r"^-?\$?\(?\d[\d,]*(?:\.\d+)?\)?$|^(?:NA|N/A|NM)$", re.I)


# -----------------------------------------------------------------------------
# Normalization helpers
# -----------------------------------------------------------------------------

def clean_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_line(value: object) -> str:
    return clean_text(value).lower()


def normalize_ticker(value: object) -> str:
    token = clean_text(value).upper().replace(" ", "")
    token = re.sub(r"[^A-Z]", "", token)
    fixes = {
        "PD": "PD", "ZS": "ZS", "AI": "AI", "WK": "WK", "OS": "OS",
        "TTAN": "TTAN", "ZM": "ZM", "ZD": "ZD",
    }
    return fixes.get(token, token)


def is_valid_ticker(ticker: str, allow_single: bool = True) -> bool:
    if not ticker or ticker in BAD_TICKERS:
        return False
    if not re.fullmatch(r"[A-Z]{1,6}", ticker):
        return False
    if len(ticker) == 1 and allow_single and ticker not in ALLOWED_SINGLE_LETTER_TICKERS:
        return False
    if len(ticker) == 1 and not allow_single:
        return False
    return True


def normalize_money(value: object, keep_dollar: bool = False) -> Optional[str]:
    """Return clean numeric text. Keep a leading '$' only for PT fields."""
    text = clean_text(value)
    if not text:
        return None
    upper = text.upper().replace(" ", "")
    if upper in {"NA", "N/A", "NM"}:
        return "NA" if upper in {"NA", "N/A"} else "NM"

    # Normalize common negative signs and remove separators.
    text = text.replace("âˆ’", "-").replace("â€“", "-").replace("â€”", "-")
    text = text.replace(",", "")
    text = re.sub(r"\s+", "", text)
    text = text.replace("$", "")
    if not text:
        return None

    # Convert accounting parentheses if seen.
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    if negative and not text.startswith("-"):
        text = "-" + text

    if not re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if not match:
            return None
        text = match.group(0)
    return f"${text}" if keep_dollar else text


def normalize_eps(value: object) -> Optional[str]:
    text = clean_text(value).upper()
    if text in {"NA", "N/A", "NM"}:
        return "NA" if text in {"NA", "N/A"} else "NM"
    return normalize_money(value, keep_dollar=False)


def looks_numeric(value: object) -> bool:
    text = clean_text(value)
    return bool(text and NUMERIC_TOKEN_RE.fullmatch(text))


# -----------------------------------------------------------------------------
# PDF geometry models
# -----------------------------------------------------------------------------

@dataclass
class SpanToken:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    font: str = ""
    flags: int = 0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2.0

    @property
    def bold(self) -> bool:
        font = self.font.lower()
        return "bold" in font or bool(self.flags & 16)


@dataclass
class ColumnBand:
    label: str
    center: float
    left: float
    right: float


@dataclass
class YearGroup:
    label: str
    years: list[str]
    bands: list[ColumnBand]


@dataclass
class HeaderSpec:
    page_number: int
    header_y: float
    year_y: float
    ticker_right: float
    price_band: Optional[ColumnBand]
    ev_band: Optional[ColumnBand]
    groups: list[YearGroup] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def find_group(self, *required: str, exclude: Iterable[str] = ()) -> Optional[YearGroup]:
        required_l = [x.lower() for x in required]
        exclude_l = [x.lower() for x in exclude]
        for group in self.groups:
            label_l = group.label.lower()
            if all(x in label_l for x in required_l) and not any(x in label_l for x in exclude_l):
                return group
        return None


# -----------------------------------------------------------------------------
# Geometry helpers
# -----------------------------------------------------------------------------

def group_tokens_by_row(tokens: list[SpanToken], y_tolerance: float = 2.2) -> list[list[SpanToken]]:
    if not tokens:
        return []
    tokens = sorted(tokens, key=lambda t: (t.y0, t.x0))
    rows: list[list[SpanToken]] = []
    current: list[SpanToken] = [tokens[0]]
    current_y = tokens[0].y0
    for token in tokens[1:]:
        if abs(token.y0 - current_y) <= y_tolerance:
            current.append(token)
            current_y = (current_y * (len(current) - 1) + token.y0) / len(current)
        else:
            rows.append(sorted(current, key=lambda t: t.x0))
            current = [token]
            current_y = token.y0
    rows.append(sorted(current, key=lambda t: t.x0))
    return rows


def row_text(row: list[SpanToken]) -> str:
    return clean_text(" ".join(t.text for t in sorted(row, key=lambda t: t.x0)))


def cell_text(row: list[SpanToken], left: float, right: float) -> str:
    pieces = [t for t in sorted(row, key=lambda t: t.x0) if left <= t.cx < right]
    return clean_text(" ".join(t.text for t in pieces))


def make_bands(labels: list[str], centers: list[float], left_edge: Optional[float] = None, right_edge: Optional[float] = None) -> list[ColumnBand]:
    if not centers:
        return []
    pairs = sorted(zip(labels, centers), key=lambda x: x[1])
    labels = [p[0] for p in pairs]
    centers = [p[1] for p in pairs]
    bands: list[ColumnBand] = []
    for i, center in enumerate(centers):
        if i == 0:
            if left_edge is not None:
                left = left_edge
            else:
                gap = centers[1] - center if len(centers) > 1 else 20
                left = center - gap / 2.0
        else:
            left = (centers[i - 1] + center) / 2.0

        if i == len(centers) - 1:
            if right_edge is not None:
                right = right_edge
            else:
                gap = center - centers[i - 1] if i > 0 else 20
                right = center + gap / 2.0
        else:
            right = (center + centers[i + 1]) / 2.0
        bands.append(ColumnBand(labels[i], center, left, right))
    return bands


def find_header_token(row: list[SpanToken], target: str) -> Optional[SpanToken]:
    """Find a header token, including split headers such as P T."""
    target_l = target.lower()
    row_sorted = sorted(row, key=lambda t: t.x0)
    for token in row_sorted:
        if token.text.lower() == target_l:
            return token

    if target_l == "pt":
        for i in range(len(row_sorted) - 1):
            if row_sorted[i].text.lower() == "p" and row_sorted[i + 1].text.lower() == "t":
                return SpanToken(
                    text="PT",
                    x0=row_sorted[i].x0,
                    y0=min(row_sorted[i].y0, row_sorted[i + 1].y0),
                    x1=row_sorted[i + 1].x1,
                    y1=max(row_sorted[i].y1, row_sorted[i + 1].y1),
                )
    return None


def is_table_like_header(text: str) -> bool:
    text_l = normalize_line(text)
    return "ticker" in text_l and "name" in text_l


# -----------------------------------------------------------------------------
# Extractor
# -----------------------------------------------------------------------------

class RBCSoftwareMasterExtractor:
    """Dynamic extractor for both RBC Weekly and Monthly Software PDFs."""

    def __init__(self, pdf_path: Path, debug: bool = False):
        self.pdf_path = Path(pdf_path)
        self.debug = debug
        self.doc = fitz.open(str(self.pdf_path))
        self.audit: list[dict[str, object]] = []
        self._page_text_cache: dict[int, str] = {}
        self._span_cache: dict[int, list[SpanToken]] = {}
        self._word_cache: dict[int, list[SpanToken]] = {}

    def close(self) -> None:
        self.doc.close()

    # ----------------------- basic PDF access -----------------------

    def page_text(self, page_index: int) -> str:
        if page_index not in self._page_text_cache:
            self._page_text_cache[page_index] = self.doc[page_index].get_text("text") or ""
        return self._page_text_cache[page_index]

    def first_lines(self, page_index: int, count: int = 12) -> list[str]:
        lines = [clean_text(x) for x in self.page_text(page_index).splitlines() if clean_text(x)]
        return lines[:count]

    def page_title(self, page_index: int) -> str:
        lines = self.first_lines(page_index, 10)
        for line in lines:
            low = line.lower()
            if "weekly software recap" in low or "monthly software valuation recap" in low:
                continue
            if re.search(r"^(coverage universe|non-gaap|rule of 40|ai universe|back office universe|design software universe|devops|front office universe|saas|security|vertical software)", low):
                return line
        return lines[0] if lines else ""

    def detect_report_type(self) -> str:
        name = self.pdf_path.name.lower()
        if "weekly" in name:
            return "weekly"
        if "monthly" in name:
            return "monthly"

        first_lines_text = normalize_line(" ".join(self.first_lines(0, 8))) if len(self.doc) else ""
        first_page = normalize_line(self.page_text(0)) if len(self.doc) else ""
        if "weekly software recap" in first_lines_text or "hedberg & jaluria weekly software" in first_lines_text:
            return "weekly"
        if "monthly software valuation recap" in first_lines_text:
            return "monthly"
        if "weekly software" in first_page:
            return "weekly"
        if "monthly software" in first_page:
            return "monthly"
        return "unknown"

    def spans(self, page_index: int) -> list[SpanToken]:
        if page_index in self._span_cache:
            return self._span_cache[page_index]
        data = self.doc[page_index].get_text("dict")
        tokens: list[SpanToken] = []
        for block in data.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = clean_text(span.get("text", ""))
                    if not text:
                        continue
                    x0, y0, x1, y1 = span["bbox"]
                    tokens.append(
                        SpanToken(
                            text=text,
                            x0=float(x0), y0=float(y0), x1=float(x1), y1=float(y1),
                            font=span.get("font", ""), flags=int(span.get("flags", 0)),
                        )
                    )
        self._span_cache[page_index] = tokens
        return tokens

    def words(self, page_index: int) -> list[SpanToken]:
        if page_index in self._word_cache:
            return self._word_cache[page_index]
        tokens: list[SpanToken] = []
        for word in self.doc[page_index].get_text("words"):
            x0, y0, x1, y1, text = word[:5]
            text = clean_text(text)
            if not text:
                continue
            tokens.append(SpanToken(text=text, x0=float(x0), y0=float(y0), x1=float(x1), y1=float(y1)))
        self._word_cache[page_index] = tokens
        return tokens

    # ----------------------- section discovery -----------------------

    def has_table_header(self, page_index: int) -> bool:
        header_text = " ".join(t.text for t in self.spans(page_index) if t.y0 < 190)
        return bool(re.search(r"\bTicker\b", header_text) and re.search(r"\bName\b", header_text))

    def find_coverage_pages(self) -> list[int]:
        pages = []
        for i in range(len(self.doc)):
            title = normalize_line(self.page_title(i))
            if title == "coverage universe" and self.has_table_header(i):
                pages.append(i)
        self.audit.append({"event": "section_pages", "section": "Coverage Universe", "pages": ",".join(str(p + 1) for p in pages)})
        return pages

    def find_sales_eps_pages(self) -> list[int]:
        pages = []
        for i in range(len(self.doc)):
            title = normalize_line(self.page_title(i))
            if title.startswith("non-gaap vs") and self.has_table_header(i):
                pages.append(i)
        self.audit.append({"event": "section_pages", "section": "Non-GAAP vs. GAAP EPS", "pages": ",".join(str(p + 1) for p in pages)})
        return pages

    def find_rule40_table_pages(self) -> list[int]:
        pages = []
        for i in range(len(self.doc)):
            title = normalize_line(self.page_title(i))
            # Include comp-group tables, exclude chart pages such as "Rule of 40 - SaaS".
            if title.startswith("rule of 40") and " in cy/" in title and self.has_table_header(i):
                pages.append(i)
        self.audit.append({"event": "section_pages", "section": "Rule of 40", "pages": ",".join(str(p + 1) for p in pages)})
        return pages

    # ----------------------- header analysis -----------------------

    def table_header_spec(self, page_index: int) -> Optional[HeaderSpec]:
        tokens = [t for t in self.words(page_index) if t.y0 < 190]
        if not tokens:
            return None

        ticker_tokens = [t for t in tokens if t.text.lower() == "ticker"]
        if not ticker_tokens:
            return None
        ticker_token = sorted(ticker_tokens, key=lambda t: t.y0)[-1]
        ticker_right = ticker_token.x1 + 6.0

        year_tokens_all = sorted([t for t in tokens if YEAR_RE.fullmatch(t.text)], key=lambda t: (t.y0, t.x0))
        if len(year_tokens_all) < 3:
            return None

        # Header pages have one line with all year labels repeated across groups.
        # Use the row with the most year labels, not simply max y, so this is
        # resilient if footnotes or other year mentions move around.
        year_rows = group_tokens_by_row(year_tokens_all, y_tolerance=3.0)
        year_row = max(year_rows, key=len)
        if len(year_row) < 3:
            return None
        year_y = sum(t.y0 for t in year_row) / len(year_row)
        year_tokens = sorted(year_row, key=lambda t: t.x0)

        date_tokens = [t for t in tokens if DATE_RE.fullmatch(t.text)]
        price_headers = [t for t in tokens if t.text.lower() == "price"]
        ev_value_headers = [t for t in tokens if t.text.lower() == "($m)"]
        ev_headers = [t for t in tokens if t.text.upper() == "EV"]

        price_center = date_tokens[0].cx if date_tokens else (price_headers[0].cx if price_headers else None)
        ev_center = ev_value_headers[0].cx if ev_value_headers else (ev_headers[0].cx if ev_headers else None)

        labels: list[str] = []
        centers: list[float] = []
        if price_center is not None:
            labels.append("Price")
            centers.append(float(price_center))
        if ev_center is not None:
            labels.append("EV")
            centers.append(float(ev_center))
        labels += [t.text.upper() for t in year_tokens]
        centers += [t.cx for t in year_tokens]

        all_bands = make_bands(labels, centers, left_edge=120.0, right_edge=760.0)
        price_band = min(all_bands, key=lambda b: abs(b.center - float(price_center))) if price_center is not None else None
        ev_band = min(all_bands, key=lambda b: abs(b.center - float(ev_center))) if ev_center is not None else None

        year_bands: list[ColumnBand] = []
        for yt in year_tokens:
            band = min(all_bands, key=lambda b, x=yt.cx: abs(b.center - x))
            year_bands.append(ColumnBand(yt.text.upper(), yt.cx, band.left, band.right))

        groups: list[YearGroup] = []
        for idx in range(0, len(year_bands), 3):
            triplet = year_bands[idx:idx + 3]
            if len(triplet) < 3:
                continue
            group_left = triplet[0].left
            group_right = triplet[-1].right
            label_tokens = [
                t for t in tokens
                if (year_y - 24.0) <= t.y0 < year_y - 1.0
                and group_left <= t.cx < group_right
                and t.text.lower() not in {"price", "ev", "ticker", "name"}
                and not DATE_RE.fullmatch(t.text)
                and t.text.lower() != "($m)"
            ]
            label = clean_text(" ".join(t.text for t in sorted(label_tokens, key=lambda t: t.x0)))
            if not label:
                label = f"Group {idx // 3 + 1}"
            groups.append(YearGroup(label=label, years=[b.label for b in triplet], bands=triplet))

        spec = HeaderSpec(
            page_number=page_index + 1,
            header_y=ticker_token.y0,
            year_y=year_y,
            ticker_right=ticker_right,
            price_band=price_band,
            ev_band=ev_band,
            groups=groups,
        )
        if self.debug:
            self.audit.append({
                "event": "header_spec",
                "page": page_index + 1,
                "title": self.page_title(page_index),
                "ticker_right": round(ticker_right, 2),
                "groups": json.dumps([{g.label: [round(b.center, 1) for b in g.bands]} for g in groups]),
            })
        return spec

    # ----------------------- row extraction -----------------------

    def extract_ticker_from_row(self, row: list[SpanToken], ticker_right: float) -> Optional[str]:
        left_tokens = [t for t in sorted(row, key=lambda t: t.x0) if t.x0 < ticker_right]
        if not left_tokens:
            return None

        pieces: list[str] = []
        for token in left_tokens:
            txt = clean_text(token.text).upper()
            if re.fullmatch(r"[A-Z]{1,6}", txt):
                pieces.append(txt)
            elif pieces:
                break
        if not pieces:
            return None

        ticker = normalize_ticker("".join(pieces))
        return ticker if is_valid_ticker(ticker) else None

    def row_is_bold(self, row: list[SpanToken], ticker_right: float, first_value_left: float) -> bool:
        # Covered company bolding is in the ticker/name area. Numeric columns can
        # also contain bold-looking glyphs in some PDFs, so ignore those.
        left_area = [t for t in row if t.x0 < max(first_value_left, ticker_right + 10.0)]
        return any(t.bold for t in left_area)

    # ----------------------- Coverage Universe -----------------------

    def extract_coverage_pt_rating(self) -> pd.DataFrame:
        pages = self.find_coverage_pages()
        records: list[dict[str, object]] = []

        for page_index in pages:
            rows = group_tokens_by_row(self.spans(page_index))
            header_row: Optional[list[SpanToken]] = None
            for row in rows:
                text = row_text(row)
                text_l = normalize_line(text)
                if "ticker" in text_l and "rating" in text_l and "name" in text_l and ("pt" in text_l or "p t" in text_l):
                    header_row = row
                    break
            if not header_row:
                self.audit.append({"event": "warning", "page": page_index + 1, "message": "Coverage header not found"})
                continue

            ticker_h = find_header_token(header_row, "ticker")
            pt_h = find_header_token(header_row, "pt")
            rating_h = find_header_token(header_row, "rating")
            name_h = find_header_token(header_row, "name")
            if not ticker_h or not pt_h or not rating_h or not name_h:
                self.audit.append({"event": "warning", "page": page_index + 1, "message": "Coverage header tokens incomplete"})
                continue

            boundaries = {
                "ticker_left": 0.0,
                "ticker_right": ticker_h.x1 + 4.0,
                "pt_right": rating_h.x0 - 4.0,
                "rating_right": rating_h.x1 + 7.0,
                "name_right": max(name_h.x1 + 80.0, 245.0),
            }

            for row in rows:
                if row[0].y0 <= header_row[0].y0 + 5.0:
                    continue
                text_l = normalize_line(row_text(row))
                if not text_l or any(skip in text_l for skip in ["rating:", "source:", "mean", "median"]):
                    continue

                ticker = normalize_ticker(cell_text(row, boundaries["ticker_left"], boundaries["ticker_right"]))
                if not is_valid_ticker(ticker):
                    continue

                rating = clean_text(cell_text(row, boundaries["pt_right"], boundaries["rating_right"])).upper().replace(" ", "")
                pt = normalize_money(cell_text(row, boundaries["ticker_right"], boundaries["pt_right"]), keep_dollar=True)
                if rating not in RATING_VALUES or not pt:
                    continue
                records.append({"Ticker": ticker, "Rating": rating, "PT": pt, "Page": page_index + 1})

        df = pd.DataFrame(records)
        if df.empty:
            return pd.DataFrame(columns=["Ticker", "Rating", "PT"])
        df = df.drop_duplicates(subset=["Ticker"], keep="first")
        return df[["Ticker", "Rating", "PT"]].reset_index(drop=True)

    # ----------------------- Sales/EPS and Rule of 40 -----------------------

    def extract_financial_table(self, mode: str) -> pd.DataFrame:
        if mode not in {"sales_eps", "rule40"}:
            raise ValueError("mode must be 'sales_eps' or 'rule40'")

        pages = self.find_sales_eps_pages() if mode == "sales_eps" else self.find_rule40_table_pages()
        records: list[dict[str, object]] = []

        for page_index in pages:
            spec = self.table_header_spec(page_index)
            if not spec:
                self.audit.append({"event": "warning", "page": page_index + 1, "message": "Financial table header spec not found"})
                continue

            revenue_group = spec.find_group("revenue", exclude={"ev/", "growth"})
            if revenue_group is None and spec.groups:
                revenue_group = spec.groups[0]
                self.audit.append({"event": "warning", "page": page_index + 1, "message": "Revenue group fallback to first group"})
            if revenue_group is None:
                self.audit.append({"event": "warning", "page": page_index + 1, "message": "No revenue group found"})
                continue

            non_gaap_group = gaap_group = None
            if mode == "sales_eps":
                non_gaap_group = spec.find_group("non-gaap", "eps", exclude={"difference", "vs."})
                gaap_group = spec.find_group("gaap", "eps", exclude={"non-gaap", "difference", "vs."})
                if non_gaap_group is None and len(spec.groups) >= 4:
                    non_gaap_group = spec.groups[3]
                    self.audit.append({"event": "warning", "page": page_index + 1, "message": "Non-GAAP EPS fallback to group 4"})
                if gaap_group is None and len(spec.groups) >= 5:
                    gaap_group = spec.groups[4]
                    self.audit.append({"event": "warning", "page": page_index + 1, "message": "GAAP EPS fallback to group 5"})

            rows = group_tokens_by_row(self.spans(page_index))
            first_value_left = min(
                [b.left for b in revenue_group.bands]
                + ([spec.price_band.left] if spec.price_band else [120.0])
            )

            for row in rows:
                if row[0].y0 <= spec.year_y + 5.0:
                    continue
                text_l = normalize_line(row_text(row))
                if not text_l:
                    continue
                if any(skip in text_l for skip in ["source:", "hedberg", "factset", "mean", "median", "monthly software", "weekly software"]):
                    continue

                ticker = self.extract_ticker_from_row(row, spec.ticker_right)
                if not ticker:
                    continue

                is_bold = self.row_is_bold(row, spec.ticker_right, first_value_left)
                record: dict[str, object] = {
                    "Ticker": ticker,
                    "IsBold": "Yes" if is_bold else "No",
                    "Page": page_index + 1,
                }

                for band in revenue_group.bands:
                    record[f"Revenue_{band.label}"] = normalize_money(cell_text(row, band.left, band.right))

                if mode == "sales_eps":
                    if non_gaap_group:
                        for band in non_gaap_group.bands:
                            record[f"NonGAAP_EPS_{band.label}"] = normalize_eps(cell_text(row, band.left, band.right))
                    if gaap_group:
                        for band in gaap_group.bands:
                            record[f"GAAP_EPS_{band.label}"] = normalize_eps(cell_text(row, band.left, band.right))
                records.append(record)

        df = pd.DataFrame(records)
        if df.empty:
            return pd.DataFrame()

        df = df.drop_duplicates(subset=["Ticker", "IsBold"], keep="first")
        df = df.drop(columns=["Page"], errors="ignore")
        return df.reset_index(drop=True)

    # ----------------------- validation and output frames -----------------------

    def validate_frames(self, coverage_df: pd.DataFrame, sales_eps_df: pd.DataFrame, rule40_df: pd.DataFrame) -> None:
        def warn(message: str, **extra: object) -> None:
            row = {"event": "validation_warning", "message": message}
            row.update(extra)
            self.audit.append(row)

        if coverage_df.empty:
            warn("Coverage Universe extraction returned zero rows")
        if sales_eps_df.empty:
            warn("Non-GAAP vs. GAAP EPS extraction returned zero rows")
        if rule40_df.empty:
            warn("Rule of 40 extraction returned zero rows")

        for name, df in [("Coverage", coverage_df), ("Sales/EPS", sales_eps_df), ("Rule of 40", rule40_df)]:
            if df.empty:
                continue
            ticker_col = "Ticker" if "Ticker" in df.columns else "Symbol"
            bad = [t for t in df[ticker_col].astype(str).tolist() if not is_valid_ticker(normalize_ticker(t))]
            if bad:
                warn(f"{name} has invalid-looking tickers", count=len(bad), examples=", ".join(bad[:10]))

        for name, df in [("Sales/EPS", sales_eps_df), ("Rule of 40", rule40_df)]:
            if df.empty:
                continue
            value_cols = [c for c in df.columns if c.startswith("Revenue_") or c.startswith("NonGAAP_EPS_") or c.startswith("GAAP_EPS_")]
            for col in value_cols:
                bad_values = [v for v in df[col].dropna().astype(str).tolist() if v not in {"NA", "NM"} and not re.fullmatch(r"-?\d+(?:\.\d+)?", v)]
                if bad_values:
                    warn(f"{name} column has non-standard values", column=col, count=len(bad_values), examples=", ".join(bad_values[:5]))

    def extract_all(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        report_type = self.detect_report_type()
        self.audit.append({"event": "report_detected", "report_type": report_type, "pdf": self.pdf_path.name, "pages": len(self.doc)})

        coverage_df = self.extract_coverage_pt_rating()
        sales_eps_df = self.extract_financial_table("sales_eps")
        rule40_df = self.extract_financial_table("rule40")
        self.validate_frames(coverage_df, sales_eps_df, rule40_df)

        s1 = coverage_df[["Ticker", "Rating", "PT"]].copy() if not coverage_df.empty else pd.DataFrame(columns=["Ticker", "Rating", "PT"])
        s1.columns = ["Symbol", "Rating", "PT/Target Price"]

        s2 = sales_eps_df[sales_eps_df["IsBold"] == "Yes"].copy() if not sales_eps_df.empty else pd.DataFrame()
        s2_tickers = set(s2["Ticker"].unique()) if not s2.empty else set()
        if not s2.empty:
            s2 = s2.drop(columns=["IsBold"])

        s3 = rule40_df[rule40_df["IsBold"] == "Yes"].copy() if not rule40_df.empty else pd.DataFrame()
        if not s3.empty:
            s3 = s3[~s3["Ticker"].isin(s2_tickers)].copy()
            s3 = s3.drop(columns=["IsBold"])

        metadata_parts: list[pd.DataFrame] = []
        if not coverage_df.empty:
            m = coverage_df.copy()
            m.insert(0, "Source Table", "Coverage Universe")
            metadata_parts.append(m)
        if not sales_eps_df.empty:
            m = sales_eps_df.copy()
            m.insert(0, "Source Table", "Non-GAAP vs. GAAP EPS")
            metadata_parts.append(m)
        if not rule40_df.empty:
            m = rule40_df.copy()
            m.insert(0, "Source Table", "Rule of 40")
            metadata_parts.append(m)
        metadata_df = pd.concat(metadata_parts, ignore_index=True) if metadata_parts else pd.DataFrame()

        self.audit.append({"event": "summary", "metric": "coverage_rows", "value": len(coverage_df)})
        self.audit.append({"event": "summary", "metric": "sales_eps_rows", "value": len(sales_eps_df)})
        self.audit.append({"event": "summary", "metric": "sales_eps_bold_rows", "value": len(s2)})
        self.audit.append({"event": "summary", "metric": "rule40_rows", "value": len(rule40_df)})
        self.audit.append({"event": "summary", "metric": "only_revenue_rows", "value": len(s3)})
        self.audit.append({"event": "summary", "metric": "metadata_rows", "value": len(metadata_df)})
        return s1, s2, s3, metadata_df


# -----------------------------------------------------------------------------
# Excel writer
# -----------------------------------------------------------------------------

def autosize_xlsx(writer: pd.ExcelWriter, sheet_name: str, df: pd.DataFrame, startrow: int = 0) -> None:
    worksheet = writer.sheets.get(sheet_name)
    if worksheet is None:
        return
    workbook = writer.book
    header_fmt = workbook.add_format({"bold": True, "bg_color": "#D9EAF7", "border": 1})
    text_fmt = workbook.add_format({"num_format": "@"})
    for col_num, value in enumerate(df.columns):
        worksheet.write(startrow, col_num, value, header_fmt)
        series = df[value].astype(str) if not df.empty else pd.Series(dtype=str)
        max_len = max([len(str(value))] + [len(str(x)) for x in series.head(300).tolist()])
        worksheet.set_column(col_num, col_num, min(max(max_len + 2, 10), 36), text_fmt)
    worksheet.freeze_panes(startrow + 1, 0)
    if not df.empty:
        worksheet.autofilter(startrow, 0, startrow + len(df), max(len(df.columns) - 1, 0))


def write_output(
    output_path: Path,
    s1: pd.DataFrame,
    s2: pd.DataFrame,
    s3: pd.DataFrame,
    metadata_df: pd.DataFrame,
    audit_df: Optional[pd.DataFrame] = None,
) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        s1.to_excel(writer, sheet_name="Symbol Rating and PT", index=False)
        autosize_xlsx(writer, "Symbol Rating and PT", s1)

        s2.to_excel(writer, sheet_name="Sales and EPS (Bold Only)", index=False)
        autosize_xlsx(writer, "Sales and EPS (Bold Only)", s2)

        s3.to_excel(writer, sheet_name="Only Revenue", index=False)
        autosize_xlsx(writer, "Only Revenue", s3)

        meta_sheet = "Metadata Reference"
        header = pd.DataFrame([["Data fetched from: Coverage Universe, Non-GAAP vs. GAAP EPS, Rule of 40"]])
        header.to_excel(writer, sheet_name=meta_sheet, index=False, header=False)
        metadata_df.to_excel(writer, sheet_name=meta_sheet, index=False, startrow=2)
        autosize_xlsx(writer, meta_sheet, metadata_df, startrow=2)
        writer.sheets[meta_sheet].set_column(0, 0, 28)

        if audit_df is not None and not audit_df.empty:
            audit_df.to_excel(writer, sheet_name="Extraction Audit", index=False)
            autosize_xlsx(writer, "Extraction Audit", audit_df)


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def default_output_path(pdf_path: Path, report_type: str = "unknown") -> Path:
    if report_type == "monthly":
        name = "MonthlySoftware_Extract.xlsx"
    elif report_type == "weekly":
        name = "WeeklySoftware_Extract.xlsx"
    else:
        name = "RBCSoftware_Extract.xlsx"
    return pdf_path.with_name(name)


def process_pdf(pdf_path: Path, output_path: Optional[Path], audit_sheet: bool, debug: bool, strict: bool = False) -> dict[str, object]:
    extractor = RBCSoftwareMasterExtractor(pdf_path, debug=debug)
    try:
        report_type = extractor.detect_report_type()
        final_output = Path(output_path) if output_path else default_output_path(pdf_path, report_type)
        s1, s2, s3, metadata_df = extractor.extract_all()
        audit_df = pd.DataFrame(extractor.audit)

        critical_warnings = audit_df[audit_df.get("event", pd.Series(dtype=str)).astype(str).eq("validation_warning")] if not audit_df.empty else pd.DataFrame()
        if strict and not critical_warnings.empty:
            messages = "; ".join(critical_warnings.get("message", pd.Series(dtype=str)).astype(str).head(5).tolist())
            raise RuntimeError(f"Strict validation failed: {messages}")

        write_output(final_output, s1, s2, s3, metadata_df, audit_df if audit_sheet else None)
        return {
            "pdf": str(pdf_path),
            "output": str(final_output),
            "report_type": report_type,
            "symbol_rating_pt_rows": len(s1),
            "sales_eps_bold_rows": len(s2),
            "only_revenue_rows": len(s3),
            "metadata_rows": len(metadata_df),
        }
    finally:
        extractor.close()


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract RBC Weekly/Monthly Software PDF data into Excel.")
    parser.add_argument("--pdf", type=Path, help="Path to one RBC Software PDF.")
    parser.add_argument("--input-dir", type=Path, help="Optional folder. Processes every PDF in the folder.")
    parser.add_argument("--output", type=Path, default=None, help="Output .xlsx path for single-PDF mode.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Output folder for --input-dir mode. Defaults to each PDF folder.")
    parser.add_argument("--audit-sheet", action="store_true", help="Add an Extraction Audit sheet to each workbook.")
    parser.add_argument("--debug", action="store_true", help="Add header geometry details to the audit data and print more diagnostics.")
    parser.add_argument("--strict", action="store_true", help="Fail if validation warnings are generated.")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    if not args.pdf and not args.input_dir:
        raise SystemExit("Provide --pdf or --input-dir")
    if args.pdf and args.input_dir:
        raise SystemExit("Use either --pdf or --input-dir, not both")

    results: list[dict[str, object]] = []
    if args.pdf:
        pdf_path = Path(args.pdf)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        result = process_pdf(pdf_path, args.output, args.audit_sheet, args.debug, args.strict)
        results.append(result)
    else:
        input_dir = Path(args.input_dir)
        if not input_dir.exists():
            raise FileNotFoundError(f"Folder not found: {input_dir}")
        pdfs = sorted(input_dir.glob("*.pdf"))
        if not pdfs:
            raise FileNotFoundError(f"No PDF files found in: {input_dir}")
        for pdf_path in pdfs:
            output_path = None
            if args.output_dir:
                # Use report-type default name plus source stem to avoid collisions.
                temp = RBCSoftwareMasterExtractor(pdf_path)
                try:
                    report_type = temp.detect_report_type()
                finally:
                    temp.close()
                base = default_output_path(pdf_path, report_type).name
                output_path = Path(args.output_dir) / f"{pdf_path.stem}_{base}"
            results.append(process_pdf(pdf_path, output_path, args.audit_sheet, args.debug, args.strict))

    for result in results:
        print(f"Saved: {result['output']}")
        print(f"  Report type: {result['report_type']}")
        print(f"  Symbol Rating and PT rows: {result['symbol_rating_pt_rows']}")
        print(f"  Sales and EPS (Bold Only) rows: {result['sales_eps_bold_rows']}")
        print(f"  Only Revenue rows: {result['only_revenue_rows']}")
        print(f"  Metadata rows: {result['metadata_rows']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from processors.base import BaseProcessor

class RBCMonthlyProcessor(BaseProcessor):
    PROCESSOR_NAME = "RBC Monthly Software"
    SUPPORTED_EXTENSIONS = [".pdf"]

    def process(self, filepath: str, job) -> str:
        job.message = "Initializing RBC Monthly Software extraction..."
        job.progress = 5

        # Initialize the new extractor
        extractor = RBCSoftwareMasterExtractor(Path(filepath), debug=False)
        try:
            job.message = "Extracting tables..."
            job.progress = 30
            s1, s2, s3, metadata_df = extractor.extract_all()
            
            job.companies_found = len(s1)
            job.progress = 85
            job.message = "Writing Excel report..."

            from datetime import datetime
            output_name = f"RBC_Monthly_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            output_path = self.output_folder / output_name

            with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
                s1.to_excel(writer, sheet_name="Symbol Rating and PT", index=False)
                autosize_xlsx(writer, "Symbol Rating and PT", s1)

                s2.to_excel(writer, sheet_name="Sales and EPS (Bold Only)", index=False)
                autosize_xlsx(writer, "Sales and EPS (Bold Only)", s2)

                s3.to_excel(writer, sheet_name="Only Revenue", index=False)
                autosize_xlsx(writer, "Only Revenue", s3)

                meta_sheet = "Metadata Reference"
                header = pd.DataFrame([["Data fetched from: Coverage Universe, Non-GAAP vs. GAAP EPS, Rule of 40"]])
                header.to_excel(writer, sheet_name=meta_sheet, index=False, header=False)
                metadata_df.to_excel(writer, sheet_name=meta_sheet, index=False, startrow=2)
                autosize_xlsx(writer, meta_sheet, metadata_df, startrow=2)
                writer.sheets[meta_sheet].set_column(0, 0, 28)

        finally:
            extractor.close()

        job.output_file = output_name
        job.progress = 100
        job.message = "RBC Monthly extraction complete."
        return output_name
