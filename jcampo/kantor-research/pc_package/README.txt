KANTOR RAG — OCR REPAIR ON YOUR PC (RTX 5070)
=============================================

One-time setup (PowerShell):
1. Install Python 3.11+ from python.org if you don't have it
   (check "Add to PATH" during install).
2. Open PowerShell in this folder and run:
   pip install torch --index-url https://download.pytorch.org/whl/cu129
   pip install transformers pillow einops addict easydict pymupdf psutil matplotlib

Run:
3. If your Kantor PDFs are NOT in Downloads, edit PDF_FOLDERS at the
   top of run_repair_ocr.py (Notepad is fine).
4. python run_repair_ocr.py
   - First run downloads the model (~7 GB), then processes ~396 pages.
   - You can stop and restart any time; it continues where it left off.

After:
5. Tell Claude it's done. The results are in the ocr_out folder;
   Claude reads them, updates the search index, and publishes it.
