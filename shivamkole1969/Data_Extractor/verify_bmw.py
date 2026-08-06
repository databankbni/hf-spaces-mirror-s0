import pdfplumber
import re

pdf_path = r"C:\Users\skole\MORNINGSTAR INC\Morningstar Mumbai - India-Earning-Estimates\Shivam\Estimates Data Extractor\EGR\EGR.pdf"

print(f"Searching for BMW in PDF: {pdf_path}")
with pdfplumber.open(pdf_path) as pdf:
    for i, page in enumerate(pdf.pages):
        text = page.extract_text()
        if text and "BMW" in text and "Rating:" in text:
            print(f"Found BMW page on PDF page {i+1}")
            print("\nPage Content:")
            print(text)
            break
