---
project_name: result_anomaly
github_url: https://github.com/neural-arun/result_anomaly
language: Python
stars: 0
topics: 
updated_at: 2026-04-03T10:05:59Z
---

# result_anomaly

> **GitHub Repository:** [https://github.com/neural-arun/result_anomaly](https://github.com/neural-arun/result_anomaly)  
> **Primary Language:** Python | **Stars:** 0 | **Forks:** 0  
> **Description:** No description provided.

---

# UPPSC PCS 2024 Statistical Audit

This repository contains the data extraction scripts and the statistical audit report for the **Uttar Pradesh Public Service Commission (UPPSC) PCS 2024 Examination**. 

Upon running a mathematical extraction on the official UPPSC Result PDFs (Prelims, Mains, and Final), a severe concentration of selections was discovered favoring the `00` and `01` roll number series. 

### Key Findings
* **The "00 & 01" Series:** 4,927 candidates generated 441 final seats. *(Selection rate: 8.95%)*
* **The "Others" (02-05 Series):** 10,139 candidates generated 492 final seats. *(Selection rate: 4.85%)*

Even though candidates from series `02-05` were more than double the size of the `00 & 01` group, both groups secured almost the exact same number of final seats. Mathematically, the `00 & 01` series obtained an excess of **+136 seats** over their statistical expectation.

For full details, please read the [report.md](report.md) file included in this repository.

---

## Verify the Data Yourself
Transparency is the core purpose of this repository. You do not have to take my word for it. You can run these scripts on your own computer to pull the exact raw numbers straight from the official UPPSC PDFs.

### Prerequisites
You need Python installed along with the `pdfplumber` library to read the PDF pages.
```bash
pip install pdfplumber
```

### 1. The Official PDFs
Ensure that the official result PDFs are placed in the same directory:
* `pre_2024.pdf`
* `mains_result.pdf`
* `final_result.pdf`

### 2. Run the Extraction Script
Run the diagnostic script to parse every single page of the PDFs. It uses Regex to pull out every unique 7-digit candidate roll number across all three stages of the exam.
```bash
python verify_extraction.py
```
This script will output the exact total candidate counts (15,066 Pre, 2,720 Mains, 933 Final), proving that the sample size is 100% accurate and no candidates were missed.

### 3. Generate the Series Breakdown
If you want to pull the exact JSON counts of every series prefix to see the breakdown yourself, run:
```bash
python extract_counts.py
```
This outputs `counts.json`, which breaks down exactly how many students from `00`, `01`, `02`, etc., survived at each individual stage.

---
*Disclaimer: All analysis is derived strictly from public data published by the UPPSC. The purpose of this repository is statistical observation and data transparency.*
