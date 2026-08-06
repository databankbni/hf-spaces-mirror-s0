"""Shared Ghostscript PDF → PNG rasterization for the offline OCR pipelines.

Both OCR engines (`ocr.py` Tesseract for prose, `got_ocr.py` GOT-OCR-2.0 for
formulas) rasterize pages the same way, so the rendering lives here once.
Ghostscript only; offline batch only (never in the request path).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class PdfRenderError(RuntimeError):
    """Raised when Ghostscript is missing or rasterization fails."""


def render_pdf_to_pngs(pdf_path: Path, out_dir: Path, *, dpi: int) -> list[Path]:
    """Render every page of *pdf_path* to ``page-NNNN.png`` in *out_dir*.

    Returns the page PNGs in page order. Raises :class:`PdfRenderError` if
    Ghostscript is unavailable or produced no pages.
    """
    ghostscript = shutil.which("gs")
    if not ghostscript:
        raise PdfRenderError("Ghostscript ('gs') not found. Install it with: brew install ghostscript")

    command = [
        ghostscript,
        "-dNOPAUSE",
        "-dBATCH",
        "-dQUIET",
        "-sDEVICE=png16m",
        f"-r{dpi}",
        f"-sOutputFile={out_dir}/page-%04d.png",
        str(pdf_path),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or b"").decode("utf-8", errors="replace").strip()
        raise PdfRenderError(
            f"Ghostscript rasterization of {pdf_path.name} failed{f': {detail}' if detail else ''}"
        ) from exc

    pages = sorted(out_dir.glob("page-*.png"))
    if not pages:
        raise PdfRenderError(f"Ghostscript produced no page images for {pdf_path.name}")
    return pages
