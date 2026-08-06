"""Reference-free OCR language ablation: does dropping `rus` reduce garble?

GRO-144 removes `rus` from the Azerbaijani-sector OCR profile on the hypothesis
that the Russian language model lets Tesseract mis-resolve stylized Latin text
into Cyrillic. We can test that hypothesis **without ground-truth transcriptions**
because the GRO-143 scorers are reference-free: more Cyrillic tokens in a
Latin-script (Azerbaijani) book = more garble, full stop.

For each book this renders a sample of pages once (Ghostscript), OCRs each page
twice — `aze+eng+rus` vs `aze+eng` — and scores both with
``cyrillic_garble_token_ratio`` + ``spaced_letter_run_count``. It prints a
per-book table with the delta. Lower garble on `aze+eng` justifies the removal;
if it does NOT come out cleaner, the data says keep `rus` — report it, don't
remove against the evidence.

Run (from apps/api), pointing at the local gitignored book PDFs:

    python -m app.ingestion.application.ocr_lang_compare \
        --book "fizika:../../data/books/derived/fizika_10_cu_sinif.ocr.pdf" \
        --book "tarix:../../data/books/derived/azerbaycan_tarixi_8_demo_v1.ocr.pdf" \
        --pages 10

Offline batch only (Ghostscript + Tesseract); never in the request path.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.ingestion.infrastructure.pdf_render import PdfRenderError, render_pdf_to_pngs
from app.platform.text_quality import (
    cyrillic_garble_token_ratio,
    spaced_letter_run_count,
)

# The two variants under test: the legacy set vs the new Azerbaijani-sector set.
WITH_RUS = ["aze", "eng", "rus"]
WITHOUT_RUS = ["aze", "eng"]


def _sample_indices(total: int, want: int) -> list[int]:
    """Evenly spaced page indices across the book's interior (skip front/back matter).

    Covers/contents/colophon pages carry little prose and skew the score, so we
    sample from the middle 80% of the book.
    """
    if total <= 0:
        return []
    lo, hi = int(total * 0.1), max(int(total * 0.9), 1)
    span = max(hi - lo, 1)
    want = min(want, span)
    step = span / want
    return [lo + int(i * step) for i in range(want)]


def _ocr_png(tesseract: str, png: Path, languages: list[str]) -> str:
    """OCR a single PNG with the given Tesseract language set (stdout, tolerant decode).

    Mirrors infrastructure/ocr.py's recognize call: run from the image's dir with
    a relative name and read stdout — the workarounds for the affected builds.
    """
    result = subprocess.run(
        [tesseract, png.name, "stdout", "-l", "+".join(languages)],
        check=True,
        capture_output=True,
        cwd=png.parent,
    )
    return result.stdout.decode("utf-8", errors="replace")


def _score_book(name: str, pdf_path: Path, *, pages: int, dpi: int, tesseract: str) -> dict[str, float]:
    if not pdf_path.exists():
        raise SystemExit(f"book {name!r}: PDF not found at {pdf_path}")

    with tempfile.TemporaryDirectory(prefix="dim-ablation-") as workdir:
        try:
            page_images = render_pdf_to_pngs(pdf_path, Path(workdir), dpi=dpi)
        except PdfRenderError as exc:
            raise SystemExit(f"book {name!r}: {exc}") from exc

        indices = _sample_indices(len(page_images), pages)
        sampled = [page_images[i] for i in indices]
        print(f"  {name}: {len(page_images)} pages rendered, scoring {len(sampled)} sampled")

        text_with = "\n".join(_ocr_png(tesseract, png, WITH_RUS) for png in sampled)
        text_without = "\n".join(_ocr_png(tesseract, png, WITHOUT_RUS) for png in sampled)

    return {
        "garble_with_rus": cyrillic_garble_token_ratio(text_with),
        "garble_without_rus": cyrillic_garble_token_ratio(text_without),
        "spaced_with_rus": float(spaced_letter_run_count(text_with)),
        "spaced_without_rus": float(spaced_letter_run_count(text_without)),
        "sampled_pages": float(len(sampled)),
    }


def _print_table(results: dict[str, dict[str, float]]) -> None:
    header = f"{'book':<14}{'garble +rus':>13}{'garble -rus':>13}{'Δ garble':>11}{'spaced +rus':>13}{'spaced -rus':>13}"
    print("\n" + header)
    print("-" * len(header))
    for name, r in results.items():
        delta = r["garble_without_rus"] - r["garble_with_rus"]
        print(
            f"{name:<14}"
            f"{r['garble_with_rus'] * 100:>12.2f}%"
            f"{r['garble_without_rus'] * 100:>12.2f}%"
            f"{delta * 100:>+10.2f}%"
            f"{int(r['spaced_with_rus']):>13d}"
            f"{int(r['spaced_without_rus']):>13d}"
        )
    print(
        "\nΔ garble negative ⇒ dropping `rus` is cleaner (the GRO-144 hypothesis). "
        "Positive ⇒ keep `rus`; report and do not remove."
    )


def _parse_book_arg(raw: str) -> tuple[str, Path]:
    if ":" not in raw:
        raise argparse.ArgumentTypeError(f"--book must be NAME:PATH, got {raw!r}")
    name, path = raw.split(":", 1)
    return name, Path(path)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="OCR language ablation: aze+eng+rus vs aze+eng.")
    parser.add_argument(
        "--book",
        action="append",
        type=_parse_book_arg,
        required=True,
        metavar="NAME:PATH",
        help="Book to score (repeatable), e.g. fizika:../../data/books/derived/fizika.ocr.pdf",
    )
    parser.add_argument("--pages", type=int, default=10, help="Pages to sample per book (default 10).")
    parser.add_argument("--dpi", type=int, default=300, help="Rasterization DPI (default 300).")
    args = parser.parse_args(argv)

    tesseract = shutil.which("tesseract")
    if not tesseract:
        raise SystemExit("Tesseract not found. Install it with: brew install tesseract tesseract-lang")

    print(f"OCR language ablation — sampling {args.pages} pages/book at {args.dpi} dpi")
    results = {
        name: _score_book(name, path, pages=args.pages, dpi=args.dpi, tesseract=tesseract)
        for name, path in args.book
    }
    _print_table(results)


if __name__ == "__main__":
    main()
