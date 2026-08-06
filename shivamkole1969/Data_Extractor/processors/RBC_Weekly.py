#!/usr/bin/env python3
"""
RBC Weekly Software PDF Extractor

Purpose
-------
Extract the same deliverables as the prior scripts, but use header-driven PDF
coordinates instead of raw row-text positions. This keeps output stable when the
page count, section locations, or minor table formatting changes.

Outputs
-------
1. Symbol Rating and PT
2. Sales and EPS (Bold Only)
3. Only Revenue
4. Metadata Reference

Usage
-----
python RBC_Weekly_Software_Extractor.py --pdf "Weekly Software.pdf" --output "WeeklySoftware_Extract.xlsx"
"""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import fitz  # PyMuPDF
import pandas as pd


BAD_TICKERS = {
    "TABLE", "MONTHLY", "WEEKLY", "SOFTWARE", "SOURCE", "RATING",
    "TICKER", "PRICE", "EV", "NAME", "RETURN", "RETURNS", "STOCK",
    "NON-GAAP", "GAAP", "MEAN", "MEDIAN", "AVERAGE", "AVG",
}

# The tables include a few real one-letter tickers. Other one-letter fragments
# are usually PDF extraction artifacts and are intentionally rejected.
ALLOWED_SINGLE_LETTER_TICKERS = {"S", "U"}

RATING_VALUES = {"OP", "SP", "UP", "R"}

YEAR_RE = re.compile(r"^CY/\d{2}[AE]?$", re.I)
DATE_RE = re.compile(r"^(?:\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}-\d{1,2}-\d{2,4})$")


def clean_text(value: object) -> str:
    """Normalize whitespace without changing the business value."""
    if value is None:
        return ""
    text = str(value).replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_line(value: object) -> str:
    return clean_text(value).lower()


def normalize_ticker(value: object) -> str:
    """Normalize PDF split tickers such as 'P D' and 'Z S'."""
    token = clean_text(value).upper().replace(" ", "")
    token = re.sub(r"[^A-Z]", "", token)
    fixes = {
        "PD": "PD", "ZS": "ZS", "AI": "AI", "WK": "WK", "OS": "OS",
        "TTAN": "TTAN", "ZM": "ZM", "ZD": "ZD",
    }
    return fixes.get(token, token)


def is_valid_ticker(ticker: str) -> bool:
    if not ticker or ticker in BAD_TICKERS:
        return False
    if not re.fullmatch(r"[A-Z]{1,6}", ticker):
        return False
    if len(ticker) == 1 and ticker not in ALLOWED_SINGLE_LETTER_TICKERS:
        return False
    return True


def normalize_money(value: object, keep_dollar: bool = False) -> Optional[str]:
    """Clean a money-like cell. By default, returns numeric text without $/commas."""
    text = clean_text(value)
    if not text:
        return None
    upper = text.upper().replace(" ", "")
    if upper in {"NA", "N/A", "NM"}:
        return "NA" if upper in {"NA", "N/A"} else "NM"

    # Convert accounting/negative forms and remove visual separators.
    text = text.replace("−", "-").replace("–", "-").replace("—", "-")
    text = text.replace(",", "")
    text = re.sub(r"\s+", "", text)
    text = text.replace("$", "")

    if not text:
        return None
    if not re.fullmatch(r"-?\(?\d+(?:\.\d+)?\)?", text):
        # Sometimes cells contain a harmless trailing marker; keep only first number.
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if not match:
            return None
        text = match.group(0)
    text = text.strip("()")
    return f"${text}" if keep_dollar else text


def normalize_eps(value: object) -> Optional[str]:
    text = clean_text(value).upper()
    if text in {"NA", "N/A", "NM"}:
        return "NA" if text in {"NA", "N/A"} else "NM"
    return normalize_money(value, keep_dollar=False)


def safe_sheet_name(name: str) -> str:
    invalid = r"[]:*?/\\"
    for ch in invalid:
        name = name.replace(ch, " ")
    return name[:31]


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
            # Maintain a stable running y for rows with tiny decimal variation.
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
    # Use center point to avoid a value bleeding into adjacent bands. This works
    # with RBC's right-aligned currency spans because both the dollar sign and
    # the number are centered inside the intended cell band.
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


class RBCWeeklySoftwareExtractor:
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

    def page_text(self, page_index: int) -> str:
        if page_index not in self._page_text_cache:
            self._page_text_cache[page_index] = self.doc[page_index].get_text("text") or ""
        return self._page_text_cache[page_index]

    def first_lines(self, page_index: int, count: int = 12) -> list[str]:
        lines = [clean_text(x) for x in self.page_text(page_index).splitlines() if clean_text(x)]
        return lines[:count]

    def page_title(self, page_index: int) -> str:
        lines = self.first_lines(page_index, 8)
        # Skip repeated report title if present; return the first section-like line.
        for line in lines:
            low = line.lower()
            if "hedberg" in low and "weekly software" in low:
                continue
            if re.search(r"^(coverage universe|non-gaap|rule of 40|devops|saas|security)", low):
                return line
        return lines[0] if lines else ""

    def spans(self, page_index: int) -> list[SpanToken]:
        if page_index in self._span_cache:
            return self._span_cache[page_index]
        page = self.doc[page_index]
        data = page.get_text("dict")
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
        """Word-level tokens with exact word boxes; used for header geometry."""
        if page_index in self._word_cache:
            return self._word_cache[page_index]
        page = self.doc[page_index]
        tokens: list[SpanToken] = []
        for w in page.get_text("words"):
            x0, y0, x1, y1, text = w[:5]
            text = clean_text(text)
            if not text:
                continue
            tokens.append(SpanToken(text=text, x0=float(x0), y0=float(y0), x1=float(x1), y1=float(y1)))
        self._word_cache[page_index] = tokens
        return tokens

    def has_table_header(self, page_index: int) -> bool:
        header_text = " ".join(t.text for t in self.spans(page_index) if t.y0 < 170)
        return bool(re.search(r"\bTicker\b", header_text) and re.search(r"\bName\b", header_text))

    def find_coverage_pages(self) -> list[int]:
        pages = []
        for i in range(len(self.doc)):
            title = normalize_line(self.page_title(i))
            if title == "coverage universe" and self.has_table_header(i):
                pages.append(i)
        return pages

    def find_sales_eps_pages(self) -> list[int]:
        pages = []
        for i in range(len(self.doc)):
            title = normalize_line(self.page_title(i))
            if title.startswith("non-gaap vs") and self.has_table_header(i):
                pages.append(i)
        return pages

    def find_rule40_table_pages(self) -> list[int]:
        pages = []
        for i in range(len(self.doc)):
            title = normalize_line(self.page_title(i))
            # Exclude chart pages such as "Rule of 40 - SaaS" and only include
            # the comp-group tables that carry "in CY/26E" / similar in title.
            if title.startswith("rule of 40 -") and " in cy/" in title and self.has_table_header(i):
                pages.append(i)
        return pages

    def table_header_spec(self, page_index: int) -> Optional[HeaderSpec]:
        tokens = [t for t in self.words(page_index) if t.y0 < 175]
        if not tokens:
            return None
        ticker_tokens = [t for t in tokens if t.text.lower() == "ticker"]
        if not ticker_tokens:
            return None
        ticker_token = sorted(ticker_tokens, key=lambda t: t.y0)[-1]
        ticker_right = ticker_token.x1 + 6.0

        # Year labels define the dynamic data columns. Split consecutive labels
        # into groups of 3 (CY/25A, CY/26E, CY/27E). This remains stable even if
        # the report pages move or column x-positions change slightly.
        year_tokens = sorted(
            [t for t in tokens if YEAR_RE.fullmatch(t.text)],
            key=lambda t: (t.y0, t.x0),
        )
        if len(year_tokens) < 3:
            return None
        # Use the lowest header line that contains most of the year labels.
        year_y = max(t.y0 for t in year_tokens)
        year_tokens = sorted([t for t in year_tokens if abs(t.y0 - year_y) <= 3.0], key=lambda t: t.x0)
        if len(year_tokens) < 3:
            return None

        date_tokens = [t for t in tokens if DATE_RE.fullmatch(t.text)]
        price_header = [t for t in tokens if t.text.lower() == "price"]
        ev_value_header = [t for t in tokens if t.text in {"($M)", "($m)"}]
        ev_header = [t for t in tokens if t.text.upper() == "EV"]
        price_center = (date_tokens[0].cx if date_tokens else (price_header[0].cx if price_header else None))
        ev_center = (ev_value_header[0].cx if ev_value_header else (ev_header[0].cx if ev_header else None))

        labels: list[str] = []
        centers: list[float] = []
        price_band = ev_band = None
        if price_center is not None:
            labels.append("Price")
            centers.append(float(price_center))
        if ev_center is not None:
            labels.append("EV")
            centers.append(float(ev_center))
        labels += [t.text.upper() for t in year_tokens]
        centers += [t.cx for t in year_tokens]

        all_bands = make_bands(labels, centers, left_edge=120.0, right_edge=760.0)
        band_by_label_index: list[ColumnBand] = all_bands
        if price_center is not None:
            price_band = min(all_bands, key=lambda b: abs(b.center - float(price_center)))
        if ev_center is not None:
            ev_band = min(all_bands, key=lambda b: abs(b.center - float(ev_center)))

        # Re-map year bands in the same order as year_tokens.
        year_bands = []
        for yt in year_tokens:
            band = min(band_by_label_index, key=lambda b, x=yt.cx: abs(b.center - x))
            year_bands.append(ColumnBand(yt.text.upper(), yt.cx, band.left, band.right))

        groups: list[YearGroup] = []
        for idx in range(0, len(year_bands), 3):
            triplet = year_bands[idx:idx + 3]
            if len(triplet) < 3:
                continue
            group_left = triplet[0].left
            group_right = triplet[-1].right
            # Group labels sit just above the year labels. Capture words centered
            # above this triplet and join them left-to-right.
            label_tokens = [
                t for t in tokens
                if (year_y - 22.0) <= t.y0 < year_y - 1.0
                and group_left <= t.cx < group_right
                and t.text.lower() not in {"price", "ev", "ticker", "name"}
                and not DATE_RE.fullmatch(t.text)
                and t.text not in {"($M)", "($m)"}
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

    def extract_ticker_from_row(self, row: list[SpanToken], ticker_right: float) -> Optional[str]:
        left_tokens = [t for t in sorted(row, key=lambda t: t.x0) if t.x0 < ticker_right]
        if not left_tokens:
            return None
        # In malformed PDFs, a ticker may appear as multiple one-letter spans.
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
        left_area = [t for t in row if t.x0 < max(first_value_left, ticker_right + 10)]
        if not left_area:
            return False
        # Use ticker/name area instead of numeric cells, because the intended
        # business definition is "covered companies in bold".
        return any(t.bold for t in left_area)

    def extract_coverage_pt_rating(self) -> pd.DataFrame:
        pages = self.find_coverage_pages()
        records: list[dict[str, object]] = []
        for page_index in pages:
            rows = group_tokens_by_row(self.spans(page_index))
            header_row = None
            for row in rows:
                texts = {t.text.lower() for t in row}
                if {"ticker", "pt", "rating", "name"}.issubset(texts):
                    header_row = row
                    break
            if not header_row:
                self.audit.append({"event": "warning", "page": page_index + 1, "message": "Coverage header not found"})
                continue

            hdr = {t.text.lower(): t for t in header_row if t.text.lower() in {"ticker", "pt", "rating", "name"}}
            # Coverage Universe left columns are compact and the Name header is
            # visually centered over a wide text column. Midpoints against the
            # Name header would swallow the first word of the company name into
            # the Rating cell, so boundaries are anchored to the actual header
            # word edges.
            boundaries = {
                "ticker_left": 0.0,
                "ticker_right": hdr["ticker"].x1 + 4.0,
                "pt_right": hdr["rating"].x0 - 4.0,
                "rating_right": hdr["rating"].x1 + 7.0,
                "name_right": 245.0,
            }
            for row in rows:
                if row[0].y0 <= header_row[0].y0 + 5:
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

    def extract_financial_table(self, mode: str) -> pd.DataFrame:
        if mode not in {"sales_eps", "rule40"}:
            raise ValueError("mode must be 'sales_eps' or 'rule40'")
        pages = self.find_sales_eps_pages() if mode == "sales_eps" else self.find_rule40_table_pages()
        records: list[dict[str, object]] = []
        for page_index in pages:
            spec = self.table_header_spec(page_index)
            if not spec:
                self.audit.append({"event": "warning", "page": page_index + 1, "message": "Header spec not found"})
                continue

            revenue_group = spec.find_group("revenue", exclude={"ev/", "growth"})
            if revenue_group is None and spec.groups:
                revenue_group = spec.groups[0]
                self.audit.append({"event": "warning", "page": page_index + 1, "message": "Revenue group fallback to first group"})

            non_gaap_group = gaap_group = None
            if mode == "sales_eps":
                non_gaap_group = spec.find_group("non-gaap", "eps", exclude={"difference", "vs."})
                gaap_group = spec.find_group("gaap", "eps", exclude={"non-gaap", "difference", "vs."})
                if non_gaap_group is None and len(spec.groups) >= 4:
                    non_gaap_group = spec.groups[3]
                    self.audit.append({"event": "warning", "page": page_index + 1, "message": "Non-GAAP EPS group fallback to group 4"})
                if gaap_group is None and len(spec.groups) >= 5:
                    gaap_group = spec.groups[4]
                    self.audit.append({"event": "warning", "page": page_index + 1, "message": "GAAP EPS group fallback to group 5"})

            if revenue_group is None:
                self.audit.append({"event": "warning", "page": page_index + 1, "message": "No revenue group found"})
                continue

            rows = group_tokens_by_row(self.spans(page_index))
            first_value_left = min([b.left for b in revenue_group.bands] + ([spec.price_band.left] if spec.price_band else [120.0]))
            for row in rows:
                if row[0].y0 <= spec.year_y + 5.0:
                    continue
                text_l = normalize_line(row_text(row))
                if not text_l:
                    continue
                if any(skip in text_l for skip in ["source:", "hedberg", "factset", "mean", "median"]):
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

        # Some PDFs repeat headers/rows on continuation pages. Preserve the first
        # occurrence for each ticker/bold state, matching the old script's output policy.
        df = df.drop_duplicates(subset=["Ticker", "IsBold"], keep="first")
        df = df.drop(columns=["Page"], errors="ignore")
        return df.reset_index(drop=True)

    def extract_all(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        coverage_df = self.extract_coverage_pt_rating()
        sales_eps_df = self.extract_financial_table("sales_eps")
        rule40_df = self.extract_financial_table("rule40")

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
        return s1, s2, s3, metadata_df


def autosize_xlsx(writer: pd.ExcelWriter, sheet_name: str, df: pd.DataFrame, startrow: int = 0) -> None:
    """Lightweight formatting that keeps the generated workbook readable."""
    worksheet = writer.sheets.get(sheet_name)
    if worksheet is None:
        return
    workbook = writer.book
    header_fmt = workbook.add_format({"bold": True, "bg_color": "#D9EAF7", "border": 1})
    for col_num, value in enumerate(df.columns):
        worksheet.write(startrow, col_num, value, header_fmt)
        series = df[value].astype(str) if not df.empty else pd.Series(dtype=str)
        max_len = max([len(str(value))] + [len(str(x)) for x in series.head(200).tolist()])
        worksheet.set_column(col_num, col_num, min(max(max_len + 2, 10), 34))
    worksheet.freeze_panes(startrow + 1, 0)



from processors.base import BaseProcessor

class RBCWeeklyProcessor(BaseProcessor):
    PROCESSOR_NAME = "RBC Weekly Software"
    SUPPORTED_EXTENSIONS = [".pdf"]

    def process(self, filepath: str, job) -> str:
        job.message = "Initializing RBC Weekly Software extraction..."
        job.progress = 5

        # Initialize the new extractor
        extractor = RBCWeeklySoftwareExtractor(Path(filepath), debug=False)
        try:
            job.message = "Extracting tables..."
            job.progress = 30
            s1, s2, s3, metadata_df = extractor.extract_all()
            
            job.companies_found = len(s1)
            job.progress = 85
            job.message = "Writing Excel report..."

            from datetime import datetime
            output_name = f"RBC_Weekly_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
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
        job.message = "RBC Weekly extraction complete."
        return output_name
