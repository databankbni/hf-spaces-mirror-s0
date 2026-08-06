"""
PET Weekly Processor - Peters & Co. Energy Commentary & Overview Tables
Extracts consolidated ticker/rating/target/CFPS data from PET weekly PDFs.

Rules implemented:
1) E&P Valuation Summary -> Ticker, Rating, Target. Production table -> CFPSD by year.
2) Infrastructure Overview Tables Summary -> Ticker, Rating, Target.
   Return on Capital and Growth -> Cash Flow per Share by year.
3) Energy Services Overview Tables -> Rating and 12 Month Target,
   with ticker codes taken from the table immediately below.

Duplicate handling: E&P rows have priority over Infrastructure rows;
Infrastructure rows have priority over Energy Services rows.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

import camelot  # type: ignore
import fitz  # PyMuPDF, type: ignore
import pandas as pd

from processors.base import BaseProcessor

# ---------------------------------------------------------------------------
# Shared types and constants
# ---------------------------------------------------------------------------
CellValue = Union[str, float, int, None]

RATING_VALUES = {"O", "SP", "U", "R/UR", "R", "UR"}
SECTION_PRIORITY = {"E&P": 1, "Infrastructure": 2, "Energy Services": 3}

YEAR_RE = re.compile(r"^(?:FY)?(?P<year>20\d{2})(?:E)?$")
TICKER_TOKEN_RE = re.compile(r"^[A-Z][A-Z0-9]*(?:\.[A-Z0-9]+)?$")


@dataclass
class RowData:
    ticker: str
    rating: str = ""
    target: CellValue = ""
    cfps: Dict[int, CellValue] = field(default_factory=dict)
    source: str = ""
    priority: int = 99


# ---------------------------------------------------------------------------
# Cell / text helpers
# ---------------------------------------------------------------------------
def _clean_cell(value: object) -> str:
    """Collapse whitespace/newlines from a Camelot cell."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _strip_footnotes(text: str) -> str:
    """Remove common footnote markers like (21), (18/23), (*), and (2)."""
    text = re.sub(r"\([^)]*\)", " ", text)
    text = text.replace("*", " ")
    return re.sub(r"\s+", " ", text).strip()


def _strict_ticker(cell: object) -> str:
    """Return a ticker if the cell is essentially only a ticker plus optional footnotes."""
    raw = _clean_cell(cell)
    if not raw:
        return ""
    cleaned = _strip_footnotes(raw)
    if not cleaned or "/" in cleaned:
        return ""
    if len(cleaned.split()) != 1:
        return ""
    token = cleaned.strip()
    if token in RATING_VALUES:
        return ""
    if TICKER_TOKEN_RE.match(token) and len(token) <= 10:
        return token
    return ""


def _parse_year_token(cell: object) -> Optional[int]:
    text = _clean_cell(cell)
    match = YEAR_RE.match(text)
    if match:
        return int(match.group("year"))
    return None


def _parse_number_or_text(value: object) -> CellValue:
    """Convert displayed values like '$10.85', '($64)', '-$40' into numbers."""
    text = _clean_cell(value)
    if not text or text.lower() in {"n/a", "na", "nm", "-"}:
        return ""
    if text in {"R/UR", "R", "UR"}:
        return text
    neg = False
    t = text
    if t.startswith("(") and t.endswith(")"):
        neg = True
        t = t[1:-1]
    t = t.replace("$", "").replace(",", "").replace("%", "").strip()
    if t.startswith("-"):
        neg = True
        t = t[1:].strip()
    try:
        number = float(t)
        if neg:
            number = -number
        return int(number) if number.is_integer() else number
    except ValueError:
        return text


# ---------------------------------------------------------------------------
# PDF / table helpers
# ---------------------------------------------------------------------------
def _find_pages(pdf_path: Path, must_have: Sequence[str], any_have: Sequence[str] = ()) -> List[int]:
    """Find 1-based PDF page numbers where all must_have terms occur."""
    doc = fitz.open(str(pdf_path))
    pages: List[int] = []
    must = [m.lower() for m in must_have]
    any_terms = [a.lower() for a in any_have]
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text").lower()
        if all(m in text for m in must) and (not any_terms or any(a in text for a in any_terms)):
            pages.append(i)
    return pages


def _read_camelot_tables(pdf_path: Path, page: int):
    return camelot.read_pdf(str(pdf_path), pages=str(page), flavor="stream", edge_tol=500, row_tol=2)


def _find_header_row(df, required_terms: Sequence[str], max_scan_rows: int = 12) -> Optional[int]:
    terms = [t.lower() for t in required_terms]
    for idx in range(min(len(df), max_scan_rows)):
        row_text = " ".join(_clean_cell(v).lower() for v in df.iloc[idx].tolist())
        if all(term in row_text for term in terms):
            return idx
    return None


def _find_col_by_header(df, header_rows: Iterable[int], term: str) -> Optional[int]:
    term_l = term.lower()
    for row_idx in header_rows:
        if row_idx < 0 or row_idx >= len(df):
            continue
        for col_idx, val in enumerate(df.iloc[row_idx].tolist()):
            if term_l in _clean_cell(val).lower():
                return col_idx
    return None


def _find_most_ticker_like_col(df, start_row: int, max_rows: Optional[int] = None) -> Optional[int]:
    end = len(df) if max_rows is None else min(len(df), start_row + max_rows)
    scores: List[Tuple[int, int]] = []
    for col_idx in range(df.shape[1]):
        score = 0
        for row_idx in range(start_row, end):
            if _strict_ticker(df.iat[row_idx, col_idx]):
                score += 1
        scores.append((score, col_idx))
    scores.sort(reverse=True)
    return scores[0][1] if scores and scores[0][0] > 0 else None


def _add_or_update(rows: Dict[str, RowData], new: RowData) -> None:
    """Add row respecting priority; lower priority number wins."""
    existing = rows.get(new.ticker)
    if existing is None or new.priority < existing.priority:
        rows[new.ticker] = new


# ---------------------------------------------------------------------------
# Section extractors
# ---------------------------------------------------------------------------
def _extract_ep_valuation(pdf_path: Path) -> Dict[str, RowData]:
    pages = _find_pages(pdf_path, must_have=["Valuation Summary", "Canadian Producers"], any_have=["U.S. Producers"])
    extracted: Dict[str, RowData] = {}
    for page in pages:
        for table in _read_camelot_tables(pdf_path, page):
            df = table.df
            header = _find_header_row(df, ["Ticker", "Target", "Rating"], max_scan_rows=12)
            if header is None:
                continue
            ticker_col = _find_most_ticker_like_col(df, header + 1)
            target_col = _find_col_by_header(df, range(max(0, header - 3), header + 2), "Target")
            rating_col = _find_col_by_header(df, range(max(0, header - 3), header + 2), "Rating")
            if ticker_col is None:
                ticker_col = 2
            if target_col is None:
                target_col = 4
            if rating_col is None:
                rating_col = 5
            if rating_col == target_col and target_col + 1 < df.shape[1]:
                rating_col = target_col + 1
            for row_idx in range(header + 1, len(df)):
                ticker = _strict_ticker(df.iat[row_idx, ticker_col])
                if not ticker:
                    continue
                rating = _clean_cell(df.iat[row_idx, rating_col]) if rating_col < df.shape[1] else ""
                rating = rating.replace(" ", "")
                if rating not in RATING_VALUES:
                    continue
                target = _parse_number_or_text(df.iat[row_idx, target_col]) if target_col < df.shape[1] else ""
                extracted[ticker] = RowData(
                    ticker=ticker, rating=rating, target=target,
                    source="E&P", priority=SECTION_PRIORITY["E&P"],
                )
    return extracted


def _extract_ep_production_cfpsd(pdf_path: Path, min_year: int = 2025) -> Dict[str, Dict[int, CellValue]]:
    pages = _find_pages(pdf_path, must_have=["Production", "Total Production", "CFPSD"])
    extracted: Dict[str, Dict[int, CellValue]] = {}
    for page in pages:
        for table in _read_camelot_tables(pdf_path, page):
            df = table.df
            header = _find_header_row(df, ["Ticker"], max_scan_rows=15)
            if header is None:
                continue
            ticker_col = _find_col_by_header(df, [header], "Ticker")
            if ticker_col is None:
                ticker_col = _find_most_ticker_like_col(df, header + 1) or 0
            year_cols: List[Tuple[int, int]] = []
            seen_years: set = set()
            for col_idx in range(ticker_col + 1, df.shape[1]):
                year = _parse_year_token(df.iat[header, col_idx])
                if year is None:
                    if year_cols:
                        break
                    continue
                if year in seen_years and year_cols:
                    break
                seen_years.add(year)
                if year >= min_year:
                    year_cols.append((year, col_idx))
            if not year_cols:
                continue
            for row_idx in range(header + 1, len(df)):
                ticker = _strict_ticker(df.iat[row_idx, ticker_col])
                if not ticker:
                    continue
                cfps = {year: _parse_number_or_text(df.iat[row_idx, col]) for year, col in year_cols}
                if any(v != "" for v in cfps.values()):
                    extracted[ticker] = cfps
    return extracted


def _extract_infra_summary(pdf_path: Path) -> Dict[str, RowData]:
    pages = _find_pages(pdf_path, must_have=["Infrastructure Overview Tables", "Pipelines / Midstream", "Rating"])
    extracted: Dict[str, RowData] = {}
    for page in pages:
        for table in _read_camelot_tables(pdf_path, page):
            df = table.df
            header = _find_header_row(df, ["Ticker", "Target", "Rating"], max_scan_rows=12)
            if header is None:
                continue
            ticker_col = _find_col_by_header(df, [header], "Ticker")
            if ticker_col is None:
                ticker_col = _find_most_ticker_like_col(df, header + 1) or 2
            target_col = _find_col_by_header(df, [header], "Target") or 4
            rating_col = _find_col_by_header(df, [header], "Rating") or 5
            if rating_col == target_col and target_col + 1 < df.shape[1]:
                rating_col = target_col + 1
            for row_idx in range(header + 1, len(df)):
                ticker = _strict_ticker(df.iat[row_idx, ticker_col])
                if not ticker:
                    continue
                rating = _clean_cell(df.iat[row_idx, rating_col]).replace(" ", "") if rating_col < df.shape[1] else ""
                if rating not in RATING_VALUES:
                    continue
                target = _parse_number_or_text(df.iat[row_idx, target_col]) if target_col < df.shape[1] else ""
                extracted[ticker] = RowData(
                    ticker=ticker, rating=rating, target=target,
                    source="Infrastructure", priority=SECTION_PRIORITY["Infrastructure"],
                )
    return extracted


def _extract_infra_cfps(pdf_path: Path, min_year: int = 2025) -> Dict[str, Dict[int, CellValue]]:
    pages = _find_pages(pdf_path, must_have=["Return on Capital and Growth", "Cash Flow per Share"])
    extracted: Dict[str, Dict[int, CellValue]] = {}
    for page in pages:
        for table in _read_camelot_tables(pdf_path, page):
            df = table.df
            header = _find_header_row(df, ["Ticker", "Cash Flow per Share"], max_scan_rows=12)
            if header is None:
                header = _find_header_row(df, ["Ticker"], max_scan_rows=12)
            if header is None:
                continue
            ticker_col = _find_col_by_header(df, [header], "Ticker")
            if ticker_col is None:
                ticker_col = 0
            year_cols: List[Tuple[int, int]] = []
            for col_idx in range(ticker_col + 1, df.shape[1]):
                year = _parse_year_token(df.iat[header, col_idx])
                if year is not None and year >= min_year:
                    year_cols.append((year, col_idx))
            if not year_cols:
                continue
            for row_idx in range(header + 1, len(df)):
                ticker = _strict_ticker(df.iat[row_idx, ticker_col])
                if not ticker:
                    continue
                cfps = {year: _parse_number_or_text(df.iat[row_idx, col]) for year, col in year_cols}
                if any(v != "" for v in cfps.values()):
                    extracted[ticker] = cfps
    return extracted


def _extract_services_summary(pdf_path: Path) -> Dict[str, RowData]:
    pages = _find_pages(pdf_path, must_have=["Energy Services Overview Tables"], any_have=["Liberty Energy", "EBITDA"])
    extracted: Dict[str, RowData] = {}
    for page in pages:
        tables = list(_read_camelot_tables(pdf_path, page))
        if not tables:
            continue
        top = None
        code_candidates = []
        for table in tables:
            df = table.df
            text = " ".join(_clean_cell(v) for v in df.values.ravel())
            if _find_header_row(df, ["Ticker", "Rating", "Target"], max_scan_rows=8) is not None:
                top = df
            if "EBITDA" in text and "Cash Flow" in text and "Ticker" in text:
                code_candidates.append(df)
        if top is None or not code_candidates:
            continue
        codes = code_candidates[-1]
        top_header = _find_header_row(top, ["Ticker", "Rating", "Target"], max_scan_rows=8)
        code_header = _find_header_row(codes, ["Ticker"], max_scan_rows=8)
        if top_header is None or code_header is None:
            continue
        rating_col = _find_col_by_header(top, [top_header], "Rating") or 1
        target_col = _find_col_by_header(top, [top_header], "Target") or 3
        code_col = _find_col_by_header(codes, [code_header], "Ticker") or 0
        top_rows: List[Tuple[str, CellValue]] = []
        for row_idx in range(top_header + 1, len(top)):
            rating = _clean_cell(top.iat[row_idx, rating_col]).replace(" ", "") if rating_col < top.shape[1] else ""
            if rating not in RATING_VALUES:
                continue
            target = _parse_number_or_text(top.iat[row_idx, target_col]) if target_col < top.shape[1] else ""
            top_rows.append((rating, target))
        code_rows: List[str] = []
        for row_idx in range(code_header + 1, len(codes)):
            ticker = _strict_ticker(codes.iat[row_idx, code_col])
            if ticker:
                code_rows.append(ticker)
        for ticker, (rating, target) in zip(code_rows, top_rows):
            extracted[ticker] = RowData(
                ticker=ticker, rating=rating, target=target,
                source="Energy Services", priority=SECTION_PRIORITY["Energy Services"],
            )
    return extracted


# ---------------------------------------------------------------------------
# Consolidation
# ---------------------------------------------------------------------------
def _consolidate(pdf_path: Path, min_year: int = 2025) -> Tuple[List[RowData], List[int]]:
    rows: Dict[str, RowData] = {}

    # Rule 1: E&P and royalty / U.S. producers.
    ep_rows = _extract_ep_valuation(pdf_path)
    ep_cfps = _extract_ep_production_cfpsd(pdf_path, min_year=min_year)
    for ticker, row in ep_rows.items():
        row.cfps.update(ep_cfps.get(ticker, {}))
        _add_or_update(rows, row)

    # Rule 2: Infrastructure.
    infra_rows = _extract_infra_summary(pdf_path)
    infra_cfps = _extract_infra_cfps(pdf_path, min_year=min_year)
    for ticker, row in infra_rows.items():
        row.cfps.update(infra_cfps.get(ticker, {}))
        _add_or_update(rows, row)

    # Rule 3: Energy Services.
    svc_rows = _extract_services_summary(pdf_path)
    for ticker, row in svc_rows.items():
        _add_or_update(rows, row)

    years = sorted({year for row in rows.values() for year in row.cfps.keys()})
    sorted_rows = sorted(rows.values(), key=lambda r: r.ticker)
    return sorted_rows, years


# ---------------------------------------------------------------------------
# Processor class
# ---------------------------------------------------------------------------
class PETWeeklyProcessor(BaseProcessor):
    PROCESSOR_NAME = "PET Weekly"
    SUPPORTED_EXTENSIONS = [".pdf"]

    def process(self, input_file: str, job) -> str:
        job.message = "Initializing PET Weekly extraction..."
        job.progress = 10

        pdf_path = Path(input_file)

        job.progress = 30
        job.message = "Extracting data from PDF (E&P, Infrastructure, Energy Services)..."

        rows, years = _consolidate(pdf_path, min_year=2025)

        job.companies_found = len(rows)

        if not rows:
            job.status = "error"
            job.message = "No data rows extracted. Check that this is a valid PET weekly PDF."
            raise ValueError("No rows extracted from PET PDF")

        job.progress = 70
        job.message = f"Writing {len(rows)} companies to Excel (years: {years})..."

        # Build a DataFrame from the consolidated data
        headers = ["Ticker", "Rating", "Target"] + [f"CFPS {yr}" for yr in years]
        data = []
        for row in rows:
            record = [row.ticker, row.rating, row.target]
            record.extend(row.cfps.get(yr, "") for yr in years)
            data.append(record)

        df = pd.DataFrame(data, columns=headers)

        output_name = f"PET_Weekly_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        output_path = self.output_folder / output_name

        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Consolidated", index=False)

        job.progress = 100
        job.message = f"Successfully extracted {len(rows)} companies across {len(years)} years."
        job.output_file = output_name
        return output_name
