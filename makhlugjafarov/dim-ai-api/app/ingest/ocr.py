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

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.ingest.pdf_render import PdfRenderError, render_pdf_to_pngs


class OcrError(RuntimeError):
    """Raised when the OCR engine is unavailable or fails on a source."""


@dataclass(frozen=True)
class OcrPage:
    page_number: int
    text: str


DEFAULT_DPI = 300


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
