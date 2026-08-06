"""Formula-aware OCR via GOT-OCR-2.0: page image → Markdown + LaTeX.

Plain OCR (Tesseract, `ocr.py`) recovers Azerbaijani *prose* but destroys
mathematical notation: `√(2−x)` → `V2-x`, `x²` → `x?`, fractions → dashes. A
math RAG with broken formulas is worthless (PROJECT_CHARTER §1). GOT-OCR-2.0
(open-source, ~580M) reads formulas correctly as LaTeX *and* the surrounding
Azerbaijani text.

Constraints (PROJECT_CHARTER §2/§7):
- Open-source and **free**. No paid vision API.
- **Offline batch only** — heavy (torch + a vision transformer). It is never
  imported at module load and never runs in the request path. Run it on a free
  GPU (Colab/Kaggle) or local; the runtime API never touches this module.

The model loads once per process (cached); pages are rendered with the shared
Ghostscript helper so page-level citations survive.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.ingest.pdf_render import PdfRenderError, render_pdf_to_pngs


class GotOcrError(RuntimeError):
    """Raised when GOT-OCR-2.0 is unavailable or fails on a source."""


@dataclass(frozen=True)
class GotOcrPage:
    page_number: int
    text: str  # Markdown with LaTeX ($...$) for formulas


MODEL_ID = "stepfun-ai/GOT-OCR-2.0-hf"
DEFAULT_DPI = 200
MAX_NEW_TOKENS = 2048

# Cached (processor, model, device, dtype); populated on first use.
_MODEL: tuple | None = None


def got_ocr_pdf(pdf_path: Path, *, dpi: int = DEFAULT_DPI) -> list[GotOcrPage]:
    """Render every page of *pdf_path* and transcribe it to Markdown + LaTeX.

    Returns one :class:`GotOcrPage` per source page, in order. Raises
    :class:`GotOcrError` if the model/deps are unavailable or rendering fails.
    """
    processor, model, device, dtype = _load_model()
    with tempfile.TemporaryDirectory(prefix="dim-gotocr-") as workdir:
        try:
            page_images = render_pdf_to_pngs(pdf_path, Path(workdir), dpi=dpi)
        except PdfRenderError as exc:
            raise GotOcrError(str(exc)) from exc
        return [
            GotOcrPage(page_number=index, text=_recognize_image(processor, model, device, dtype, png))
            for index, png in enumerate(page_images, start=1)
        ]


def _load_model() -> tuple:
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    try:
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor
    except ImportError as exc:
        raise GotOcrError(
            "GOT-OCR-2.0 needs torch + transformers. Install the ingestion extras: "
            "cd apps/api && pip install -e '.[ingestion]'"
        ) from exc

    if torch.cuda.is_available():
        device = "cuda"
    elif getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"
    dtype = torch.float32 if device == "cpu" else torch.float16

    processor = AutoProcessor.from_pretrained(MODEL_ID)
    model = AutoModelForImageTextToText.from_pretrained(MODEL_ID, dtype=dtype).to(device).eval()
    _MODEL = (processor, model, device, dtype)
    return _MODEL


def _recognize_image(processor, model, device, dtype, png_path: Path) -> str:
    import torch
    from PIL import Image

    image = Image.open(png_path).convert("RGB")
    # format=True → GOT-OCR2 emits formatted Markdown + LaTeX (vs raw text).
    inputs = processor(image, return_tensors="pt", format=True).to(device)
    if "pixel_values" in inputs:
        inputs["pixel_values"] = inputs["pixel_values"].to(dtype)
    with torch.no_grad():
        generated = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=False)
    new_tokens = generated[0, inputs["input_ids"].shape[1]:]
    return processor.decode(new_tokens, skip_special_tokens=True).strip()
