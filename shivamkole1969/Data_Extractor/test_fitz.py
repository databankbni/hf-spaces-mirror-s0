import fitz
import pdfplumber
import time

filepath = r"C:\Users\skole\MORNINGSTAR INC\Morningstar Mumbai - India-Earning-Estimates\Shivam\Raw\RBC\RBC Software\RBC Monthly Software\Monthly Software.pdf"

t0 = time.time()
page_texts_fitz = []
try:
    with fitz.open(filepath) as doc:
        for page in doc:
            page_texts_fitz.append(page.get_text())
    print("fitz time:", time.time() - t0)
except Exception as e:
    print("fitz error:", e)

t0 = time.time()
page_texts_plumber = []
try:
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            page_texts_plumber.append(page.extract_text() or "")
    print("plumber time:", time.time() - t0)
except Exception as e:
    print("plumber error:", e)

for i, raw_text in enumerate(page_texts_fitz):
    lines = [x.strip() for x in raw_text.split("\n") if x.strip()]
    first_lines = [x.lower() for x in lines[:10]]
    if any("rule of 40" in x for x in first_lines):
        print("fitz found rule of 40 on page", i)
        break

for i, raw_text in enumerate(page_texts_plumber):
    lines = [x.strip() for x in raw_text.split("\n") if x.strip()]
    first_lines = [x.lower() for x in lines[:10]]
    if any("rule of 40" in x for x in first_lines):
        print("plumber found rule of 40 on page", i)
        break
