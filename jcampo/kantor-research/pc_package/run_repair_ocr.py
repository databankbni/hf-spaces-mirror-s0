"""Kantor RAG — bulk OCR of damaged pages on the local GPU (RTX 5070).

What it does:
1. Reads pages_to_fix.json (list of works + damaged page numbers).
2. Finds each work's PDF by fuzzy title match under the folders in PDF_FOLDERS.
3. Renders the damaged pages and OCRs them with baidu/Unlimited-OCR.
4. Saves clean text to ocr_out/<key>/p<N>.md and a report to ocr_out/report.txt.

Run:  python run_repair_ocr.py
Stop/restart any time — finished pages are skipped.
"""
import os, re, json, difflib, tempfile

# ── EDIT THIS if your Kantor PDFs live somewhere else ──────────────
PDF_FOLDERS = [
    os.path.expanduser("~/Downloads"),
    os.path.expanduser("~/Downloads/Kantor"),
]
DPI = 200

import fitz  # pymupdf
import torch
from transformers import AutoModel, AutoTokenizer

def norm(s):
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).split()

def find_pdf(title, year, pdfs):
    """Fuzzy match a work title against PDF filenames."""
    twords = set(norm(title))
    best, best_score = None, 0.0
    for path in pdfs:
        name = os.path.splitext(os.path.basename(path))[0]
        nwords = set(norm(name))
        if not nwords:
            continue
        overlap = len(twords & nwords) / max(len(twords), 1)
        ratio = difflib.SequenceMatcher(None, " ".join(norm(title)),
                                        " ".join(norm(name))).ratio()
        score = max(overlap, ratio)
        if str(year) in name:
            score += 0.15
        if score > best_score:
            best, best_score = path, score
    return (best, best_score) if best_score >= 0.55 else (None, best_score)

def main():
    works = json.load(open("pages_to_fix.json", encoding="utf-8"))
    pdfs = []
    for folder in PDF_FOLDERS:
        for root, _, files in os.walk(folder):
            pdfs += [os.path.join(root, f) for f in files if f.lower().endswith(".pdf")]
    print(f"{len(pdfs)} PDFs found under {PDF_FOLDERS}")

    print("Loading model (first run downloads ~7 GB)...")
    tok = AutoTokenizer.from_pretrained("baidu/Unlimited-OCR", trust_remote_code=True)
    model = AutoModel.from_pretrained("baidu/Unlimited-OCR", trust_remote_code=True,
                                      use_safetensors=True, torch_dtype=torch.bfloat16)
    model = model.eval().cuda()

    os.makedirs("ocr_out", exist_ok=True)
    report = []
    for w in works:
        outdir = os.path.join("ocr_out", w["key"])
        pending = [p for p in w["pages"]
                   if not os.path.exists(os.path.join(outdir, f"p{p}.md"))]
        if not pending:
            report.append(f"DONE   {w['title']}")
            continue
        pdf, score = find_pdf(w["title"], w["year"], pdfs)
        if not pdf:
            report.append(f"NOPDF  {w['title']} (best score {score:.2f})")
            print(f"!! PDF not found: {w['title']}")
            continue
        os.makedirs(outdir, exist_ok=True)
        doc = fitz.open(pdf)
        print(f"== {w['title']} -> {os.path.basename(pdf)} ({len(pending)} pages)")
        for p in pending:
            if p < 1 or p > len(doc):
                report.append(f"BADPG  {w['title']} p{p} (pdf has {len(doc)})")
                continue
            img = os.path.join(tempfile.gettempdir(), "kantor_page.png")
            doc[p-1].get_pixmap(matrix=fitz.Matrix(DPI/72, DPI/72)).save(img)
            with tempfile.TemporaryDirectory() as td:
                model.infer(tok, prompt="<image>document parsing.",
                            image_file=img, output_path=td,
                            base_size=1024, image_size=640, crop_mode=True,
                            max_length=32768,
                            no_repeat_ngram_size=35, ngram_window=128,
                            save_results=True)
                # the model writes result files into output_path; grab the text
                text = ""
                for f in os.listdir(td):
                    if f.endswith((".md", ".txt")):
                        text = open(os.path.join(td, f), encoding="utf-8").read()
                        break
            open(os.path.join(outdir, f"p{p}.md"), "w", encoding="utf-8").write(text)
            print(f"   p{p}: {len(text)} chars")
        report.append(f"OK     {w['title']}")

    open("ocr_out/report.txt", "w", encoding="utf-8").write("\n".join(report))
    print("\nFinished. See ocr_out/report.txt — send ocr_out back to Claude to update the index.")

if __name__ == "__main__":
    main()
