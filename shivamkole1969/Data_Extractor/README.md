---
title: Estimates Data Extractor
emoji: 📈
colorFrom: indigo
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Estimates Data Extractor

A professional tool for extracting financial estimate data from broker research reports (PDF and Excel) into standardized Excel formats.

## Supported Brokers
- **EGR**
- **TAS**
- **HAY**
- **RJ (Raymond James Monthly)**
- **UBS Global**

## Features
- **Drag & Drop**: Simply drop your report files to start extraction.
- **URL Processing**: Paste a direct link to a report.
- **Smart Mapping**: Automatically maps data points based on broker-specific logic.
- **Modern UI**: Dark mode, glassmorphism, and real-time progress tracking.

## Technology Stack
- **Backend**: Python (Flask)
- **Data Engineering**: Pandas, OpenPyXL
- **PDF Extraction**: PyMuPDF (fitz), pdfplumber
- **Frontend**: Vanilla HTML/JS/CSS (Modern Aesthetic)
- **Deployment**: Docker on Hugging Face Spaces
