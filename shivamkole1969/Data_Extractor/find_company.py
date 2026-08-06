import pdfplumber
import re

pdf_path = r"C:\Users\skole\MORNINGSTAR INC\Morningstar Mumbai - India-Earning-Estimates\Shivam\Estimates Data Extractor\EGR\EGR.pdf"
company_name = "Hermes International"

with pdfplumber.open(pdf_path) as pdf:
    for i, page in enumerate(pdf.pages):
        text = page.extract_text()
        if text and company_name.lower() in text.lower():
            print(f"Company '{company_name}' found on page {i+1}")
            print("\nPage Content Preview:")
            print(text[:1000])
            break
