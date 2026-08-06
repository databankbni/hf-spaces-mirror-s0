"""Render-and-recognize OCR for PDFs whose embedded text layer is unusable.

Some Azerbaijani textbook PDFs ship with custom/CID-keyed fonts and no
`ToUnicode` map, so raw extraction (`pypdf`) yields mojibake — the text is
*present* but maps to the wrong code points. The only reliable recovery is to
rasterize each page and OCR the pixels.

This module deliberately does **not** use `ocrmypdf`: on several Tesseract
builds its image hand-off fails (`tesseract` receives the literal string
`"PNG"` as a filename). Driving Ghostscript + Tesseract directly is both more
robust and gives us one text block per page, so page-level citations survive.

Engine: Ghostscript rasterizes each page to PNG; Tesseract recognizes each PNG,
writing to **stdout** (its file-output path is the part that is unreliable).
GPU is never involved; this is offline batch ingestion only.
"""

from __future__ import annotations

import csv
import io
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from statistics import median

from app.ingestion.domain.models import Block
from app.ingestion.infrastructure.pdf_render import PdfRenderError, render_pdf_to_pngs


class OcrError(RuntimeError):
    """Raised when the OCR engine is unavailable or fails on a source."""


@dataclass(frozen=True)
class OcrPage:
    page_number: int
    text: str


@dataclass(frozen=True)
class OcrLayoutPage:
    page_number: int
    text: str
    blocks: list[Block]
    ocr_confidence: float | None = None


DEFAULT_DPI = 300
LOW_CONFIDENCE_WORD_THRESHOLD = 50.0
OCR_HEADING_HEIGHT_RATIO = 1.25
OCR_HEADING_MAX_WORDS = 12


def ocr_pdf(pdf_path: Path, *, languages: list[str], dpi: int = DEFAULT_DPI) -> list[OcrPage]:
    """Rasterize every page of *pdf_path* and OCR it, preserving page order.

    Returns one :class:`OcrPage` per source page. Raises :class:`OcrError` if
    Ghostscript or Tesseract is missing, or if rasterization produced no pages.
    """
    tesseract = shutil.which("tesseract")
    if not tesseract:
        raise OcrError("Tesseract not found. Install it with: brew install tesseract tesseract-lang")

    language_arg = "+".join(languages) if languages else "eng"

    with tempfile.TemporaryDirectory(prefix="dim-ocr-") as workdir:
        try:
            page_images = render_pdf_to_pngs(pdf_path, Path(workdir), dpi=dpi)
        except PdfRenderError as exc:
            raise OcrError(str(exc)) from exc
        return [
            OcrPage(page_number=index, text=_recognize_png(tesseract, png, language_arg))
            for index, png in enumerate(page_images, start=1)
        ]


def ocr_pdf_layout(pdf_path: Path, *, languages: list[str], dpi: int = DEFAULT_DPI) -> list[OcrLayoutPage]:
    """Rasterize every page and OCR it via Tesseract TSV, preserving layout.

    This is the GRO-155 replacement for the legacy ``force_ocr`` flattening
    path. It keeps the same Ghostscript/Tesseract execution model but emits
    line-level Blocks with bbox, confidence, and DPI-normalised font estimates.
    """
    tesseract = shutil.which("tesseract")
    if not tesseract:
        raise OcrError("Tesseract not found. Install it with: brew install tesseract tesseract-lang")

    language_arg = "+".join(languages) if languages else "eng"

    with tempfile.TemporaryDirectory(prefix="dim-ocr-") as workdir:
        try:
            page_images = render_pdf_to_pngs(pdf_path, Path(workdir), dpi=dpi)
        except PdfRenderError as exc:
            raise OcrError(str(exc)) from exc
        return [
            _recognize_png_layout(tesseract, png, language_arg, page_number=index, dpi=dpi)
            for index, png in enumerate(page_images, start=1)
        ]


def _recognize_png(tesseract: str, png: Path, language_arg: str) -> str:
    # Two non-obvious workarounds for the affected Tesseract/Leptonica builds:
    #  1. Run from the image's directory with a *relative* filename — Leptonica
    #     fails to open absolute paths ("image file not found") on these builds.
    #  2. Write to stdout, not a sidecar file: the file-output path is unreliable.
    result = _run(
        [tesseract, png.name, "stdout", "-l", language_arg],
        what=f"Tesseract OCR of {png.name}",
        cwd=png.parent,
    )
    # Decode tolerantly: stdout is OCR'd UTF-8 text, but some Tesseract builds
    # emit stray non-UTF-8 bytes on stderr; never let that crash the run.
    return result.stdout.decode("utf-8", errors="replace")


def coalesce_ocr_layout_blocks(blocks: list[Block]) -> list[Block]:
    """Merge per-line TSV blocks into passage blocks (force_ocr fragmentation fix).

    ``_blocks_from_tesseract_tsv`` emits one Block per OCR *line*. On garbled
    scans the per-line font-height estimate is noisy, so many ordinary body lines
    exceed ``OCR_HEADING_HEIGHT_RATIO`` and get flagged as heading candidates.
    Downstream, segmentation starts a new section at every heading, so a single
    page shatters into ~8 micro-sections and the chunker emits a swarm of
    one-line chunks (observed on Kimya force_ocr: 1583 chunks, median 83 chars).

    This pass folds the line stream into coherent passages, keyed on the heading
    signal rather than Tesseract's unreliable ``par_num`` (which can group a
    heading with the body line beneath it):

    * a run of consecutive *body* lines -> one passage block;
    * a lone heading line -> kept as-is (a real heading is a single short, large
      line followed by body);
    * a run of >=2 consecutive *heading-candidate* lines is the garble tell: it is
      merged, and unless it is a genuine short multi-line title (<=2 lines and
      <= ``OCR_HEADING_MAX_WORDS`` words) it is **demoted** to body. Demotion also
      caps the font estimate so the ``heading.py`` absolute point-size fallback
      cannot re-promote it.

    Pure and deterministic; a single block (or empty input) is returned untouched
    so already-coherent pages keep byte-identical metadata.
    """
    if len(blocks) < 2:
        return blocks

    out: list[Block] = []
    run: list[Block] = []
    run_flag: bool | None = None

    def _flush() -> None:
        if not run:
            return
        if len(run) == 1:
            out.append(run[0])
            return
        out.append(_merge_layout_run(run, heading_run=bool(run_flag)))

    for block in blocks:
        flag = bool(block.metadata.get("is_ocr_heading_candidate"))
        if run and flag != run_flag:
            _flush()
            run = []
        run.append(block)
        run_flag = flag
    _flush()
    return out


def _merge_layout_run(run: list[Block], *, heading_run: bool) -> Block:
    """Fold a run of same-band line blocks into one passage block."""
    text = "\n".join(b.text.strip() for b in run if b.text.strip())
    bboxes = [b.bbox for b in run if b.bbox]
    bbox = (
        [
            min(b[0] for b in bboxes),
            min(b[1] for b in bboxes),
            max(b[2] for b in bboxes),
            max(b[3] for b in bboxes),
        ]
        if bboxes
        else None
    )

    def _meta_sum(key: str, default: float = 0.0) -> float:
        return sum(float(b.metadata.get(key, default) or 0) for b in run)

    line_count = int(_meta_sum("line_count", 1)) or len(run)
    word_count = int(_meta_sum("word_count")) or sum(len(b.text.split()) for b in run)
    max_size = max(float(b.metadata.get("max_size", 0) or 0) for b in run)
    max_ratio = max(float(b.metadata.get("ocr_height_ratio", 0) or 0) for b in run)
    page_median = next(
        (b.metadata["page_median_word_height"] for b in run if b.metadata.get("page_median_word_height")),
        0,
    )

    # A genuine multi-line title is short; anything longer in a "heading" run is a
    # big-font passage or pure OCR garble -> body.
    is_title = heading_run and line_count <= 2 and word_count <= OCR_HEADING_MAX_WORDS
    if heading_run and not is_title:
        # Demote: present body-sized font so heading.py signal-3 (max_size > 14)
        # cannot re-promote the merged passage.
        body_size = round(max_size / max_ratio, 2) if max_ratio >= 1.0 else max_size
        height_ratio = 1.0
        heading_candidate = False
        font_size = body_size
    else:
        height_ratio = max_ratio
        heading_candidate = is_title
        font_size = max_size

    return Block(
        type="text",
        text=text,
        page=run[0].page,
        bbox=bbox,
        reading_order=run[0].reading_order,
        confidence=round(sum(b.confidence for b in run) / len(run), 4),
        method=run[0].method,
        metadata={
            "estimated_font_size_pt": font_size,
            "max_size": font_size,
            "line_count": line_count,
            "word_count": word_count,
            "mean_word_confidence": round(_meta_sum("mean_word_confidence") / len(run), 1),
            "low_confidence_word_count": int(_meta_sum("low_confidence_word_count")),
            "page_median_word_height": page_median,
            "ocr_height_ratio": round(height_ratio, 3),
            "is_ocr_heading_candidate": heading_candidate,
            "is_bold": any(bool(b.metadata.get("is_bold")) for b in run),
            "coalesced_line_blocks": len(run),
        },
    )


def _recognize_png_layout(
    tesseract: str, png: Path, language_arg: str, *, page_number: int, dpi: int
) -> OcrLayoutPage:
    result = _run(
        [tesseract, png.name, "stdout", "-l", language_arg, "tsv"],
        what=f"Tesseract TSV OCR of {png.name}",
        cwd=png.parent,
    )
    tsv_text = result.stdout.decode("utf-8", errors="replace")
    blocks = coalesce_ocr_layout_blocks(
        _blocks_from_tesseract_tsv(tsv_text, page_number=page_number, dpi=dpi)
    )
    if blocks:
        text = "\n".join(block.text for block in blocks)
        page_confidence = sum(block.confidence for block in blocks) / len(blocks)
        return OcrLayoutPage(
            page_number=page_number,
            text=text,
            blocks=blocks,
            ocr_confidence=round(page_confidence * 100, 1),
        )

    fallback_text = _recognize_png(tesseract, png, language_arg)
    fallback_block = _fallback_text_block(fallback_text, page_number=page_number)
    return OcrLayoutPage(
        page_number=page_number,
        text=fallback_text,
        blocks=[fallback_block] if fallback_block else [],
        ocr_confidence=fallback_block.confidence * 100 if fallback_block else None,
    )


def _blocks_from_tesseract_tsv(tsv_text: str, *, page_number: int, dpi: int) -> list[Block]:
    rows = csv.DictReader(io.StringIO(tsv_text), delimiter="\t")
    line_words: dict[tuple[str, str, str, str], list[dict[str, float | str]]] = {}
    all_heights: list[float] = []

    for row in rows:
        if row.get("level") != "5":
            continue
        word = (row.get("text") or "").strip()
        if not word:
            continue
        try:
            conf = float(row.get("conf") or -1)
            left = float(row.get("left") or 0)
            top = float(row.get("top") or 0)
            width = float(row.get("width") or 0)
            height = float(row.get("height") or 0)
        except ValueError:
            continue
        if conf < 0:
            continue

        key = (
            row.get("page_num") or "1",
            row.get("block_num") or "0",
            row.get("par_num") or "0",
            row.get("line_num") or "0",
        )
        line_words.setdefault(key, []).append(
            {
                "text": word,
                "conf": conf,
                "left": left,
                "top": top,
                "right": left + width,
                "bottom": top + height,
                "height": height,
            }
        )
        if height > 0:
            all_heights.append(height)

    page_median_height = median(all_heights) if all_heights else 0.0
    ordered_lines = sorted(
        (words for words in line_words.values() if words),
        key=lambda words: (min(float(w["top"]) for w in words), min(float(w["left"]) for w in words)),
    )

    blocks: list[Block] = []
    for reading_order, words in enumerate(ordered_lines, start=1):
        text = " ".join(str(w["text"]) for w in words)
        heights = [float(w["height"]) for w in words if float(w["height"]) > 0]
        confs = [float(w["conf"]) for w in words]
        line_height = median(heights) if heights else 0.0
        estimated_font_size = line_height * 72 / dpi if dpi else 0.0
        height_ratio = line_height / page_median_height if page_median_height else 0.0
        is_heading_candidate = (
            page_median_height > 0
            and height_ratio >= OCR_HEADING_HEIGHT_RATIO
            and len(words) <= OCR_HEADING_MAX_WORDS
        )
        low_confidence_count = sum(1 for conf in confs if conf < LOW_CONFIDENCE_WORD_THRESHOLD)
        mean_confidence = sum(confs) / len(confs)

        blocks.append(
            Block(
                type="text",
                text=text,
                page=page_number,
                bbox=[
                    min(float(w["left"]) for w in words),
                    min(float(w["top"]) for w in words),
                    max(float(w["right"]) for w in words),
                    max(float(w["bottom"]) for w in words),
                ],
                reading_order=reading_order,
                confidence=round(mean_confidence / 100, 4),
                method="force_ocr_tsv",
                metadata={
                    "estimated_font_size_pt": round(estimated_font_size, 2),
                    "max_size": round(estimated_font_size, 2),
                    "line_count": 1,
                    "word_count": len(words),
                    "mean_word_confidence": round(mean_confidence, 1),
                    "low_confidence_word_count": low_confidence_count,
                    "median_word_height": round(line_height, 2),
                    "page_median_word_height": round(page_median_height, 2),
                    "ocr_height_ratio": round(height_ratio, 3),
                    "is_ocr_heading_candidate": is_heading_candidate,
                    "is_bold": False,
                },
            )
        )
    return blocks


def _fallback_text_block(text: str, *, page_number: int) -> Block | None:
    if not text.strip():
        return None
    return Block(
        type="text",
        text=text,
        page=page_number,
        reading_order=1,
        confidence=0.8,
        method="force_ocr_text_fallback",
        metadata={"fallback_reason": "empty_tesseract_tsv"},
    )


def _run(command: list[str], *, what: str, cwd: Path | None = None) -> subprocess.CompletedProcess[bytes]:
    # capture as bytes (no text=True): strict UTF-8 decoding of a binary-ish
    # stderr would otherwise raise UnicodeDecodeError mid-run.
    try:
        return subprocess.run(command, check=True, capture_output=True, cwd=cwd)
    except FileNotFoundError as exc:  # pragma: no cover - guarded by which() above
        raise OcrError(f"{what} failed: executable not found") from exc
    except subprocess.CalledProcessError as exc:
        raw = exc.stderr or exc.stdout or b""
        detail = raw.decode("utf-8", errors="replace").strip()
        raise OcrError(f"{what} failed{f': {detail}' if detail else ''}") from exc
