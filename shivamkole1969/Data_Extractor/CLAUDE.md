# CLAUDE.md — Estimates Data Extractor

> [!CAUTION]
> ## 🔒 MANDATORY SAFETY POLICY — READ BEFORE ANY ACTION
>
> **Password-protected destructive actions.** The following actions are classified as **HIGH-IMPACT** and require the user to provide the safety password before the AI agent proceeds:
>
> - Deleting any file or directory
> - Removing or renaming any processor (`.py` files in `processors/`)
> - Modifying `app.py`, `base.py`, `registry.py`, or `__init__.py` with more than 10 lines changed
> - Rewriting, refactoring, or replacing any existing processor file
> - Altering `.gitignore`, `Dockerfile`, `requirements.txt` in ways that remove entries
> - Running `git reset`, `git revert`, `git push --force`, or any destructive git command
> - Bulk-editing more than 3 files in a single operation
> - Removing or overwriting backup folders
>
> **Before executing any high-impact action, the AI agent MUST:**
> 1. Display a ⚠️ WARNING to the user explaining exactly what will be changed/deleted
> 2. Ask the user to confirm by providing the safety password
> 3. Only proceed if the password matches exactly
>
> **Small changes are allowed without password:** Adding new processor files, minor bug fixes (< 10 lines), adding new entries to registry, updating CLAUDE.md, creating backups, git add/commit/push (non-force).
>
> **If no password is provided or it is incorrect, REFUSE the action and explain why.**

## Project Overview

Flask web app that extracts financial estimates data from broker PDF reports into Excel/CSV.
Deployed to **Hugging Face Spaces** and runs locally via `START_APP.bat`.

- **Entry point**: `app.py` (Flask, port 7860)
- **UI**: `templates/index.html` + `static/`
- **Python**: 3.10+ (Spyder environment locally)

## Remotes

| Name     | URL |
|----------|-----|
| `origin` | `https://github.com/Shivamkole1969/Data-Extractor.git` |
| `hf`     | `https://huggingface.co/spaces/shivamkole1969/Data_Extractor` |

Push to both after every feature: `git push origin main && git push hf main`

## Architecture

```
app.py                    ← Flask server, job queue, upload/download/status APIs
processors/
  base.py                 ← BaseProcessor (abstract). Subclasses implement process(filepath, job) → output_filename
  registry.py             ← PROCESSORS dict, get_report_folder(), get_available_processors()
  EGR.py, TAS.py, ...     ← One file per broker/report type
```

### How Processors Work

1. Extend `BaseProcessor` from `processors/base.py`
2. Set `PROCESSOR_NAME` (display label) and `SUPPORTED_EXTENSIONS` (e.g. `[".pdf"]`)
3. Implement `process(self, filepath: str, job) -> str` that:
   - Updates `job.message`, `job.progress` (0-100), `job.companies_found`
   - Writes output file to `self.output_folder`
   - Returns the output filename (just the name, not full path)
4. Register in `registry.py`:
   - Import at top
   - Add to `PROCESSORS` dict
   - Add folder mapping in `get_report_folder()` if the folder path differs from the key
5. `BaseProcessor` provides `get_groq_client()` and `call_llm()` for LLM-based extraction (not all processors use these)

### Adding a New Processor — Checklist

```python
# processors/MY_NEW.py
from processors.base import BaseProcessor

class MyNewProcessor(BaseProcessor):
    PROCESSOR_NAME = "My Report Name"
    SUPPORTED_EXTENSIONS = [".pdf"]

    def process(self, filepath: str, job) -> str:
        job.message = "Starting..."
        job.progress = 5
        # ... extraction logic ...
        output_name = f"MyReport_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        output_path = self.output_folder / output_name
        # ... write Excel with openpyxl ...
        wb.save(str(output_path))
        job.output_file = output_name
        job.progress = 100
        return output_name
```

```python
# registry.py — add import + entry
from processors.MY_NEW import MyNewProcessor
PROCESSORS = { ..., "My Report Name": MyNewProcessor }
# folder_map in get_report_folder() if needed
```

## Current Processors

| Key in PROCESSORS                | Class                          | File                      |
|----------------------------------|--------------------------------|---------------------------|
| EGR                              | EGRProcessor                   | EGR.py                    |
| TAS Daily Brief                  | TASProcessor                   | TAS.py                    |
| TAS Monthly Report               | TASMonthlyProcessor            | TAS_Monthly.py            |
| HAY                              | HAYProcessor                   | HAY.py                    |
| RJ Monthly                       | RJProcessor                    | RJ.py                     |
| UBS Global                       | UBSProcessor                   | UBS.py                    |
| RBC Monthly Software             | RBCMonthlyProcessor            | RBC_Monthly.py            |
| RBC Weekly Software              | RBCWeeklyProcessor             | RBC_Weekly.py             |
| RBC Global Financial Weekly      | RBCGlobalWeeklyProcessor       | RBC_Global_Weekly.py      |
| RBC Perlin's Ponderings          | RBCPerlinsPonderingsProcessor  | RBC_Perlins_Ponderings.py |
| MNCS                             | MNCSProcessor                  | MNCS.py                   |
| TD CDN Weekly Metals & Mining    | TDCDNWeeklyProcessor           | TD_CDN_Weekly.py          |
| CA Daily Gold                    | CADailyGoldProcessor           | CA_Daily_Gold.py          |
| RBC News from Nashville          | RBCNewsNashvilleProcessor      | RBC_News_Nashville.py     |
| PET Weekly                       | PETWeeklyProcessor             | PET_Weekly.py             |

## Folder Structure for Report Data

PDF/Excel input files live under broker subfolders (e.g. `RBC/`, `EGR/`).
These folders are **gitignored** — only processor code ships.
Folder mapping is in `registry.py:get_report_folder()`.

RBC subfolder structure:
```
RBC/
  RBC Software/
    RBC Monthly Software/
    RBC Weekly software/
  Global Financial Weekly/
  Perlin's Ponderings/
  News from nashville/        ← NEW (being added)
```

## Key Dependencies

`flask`, `pdfplumber`, `openpyxl`, `groq`, `pandas`, `pymupdf (fitz)`, `camelot-py[cv]`, `opencv-python-headless`, `requests`

## .gitignore Notes

- All `*.pdf`, `*.xlsx`, `*.csv` are ignored
- All broker data folders (`EGR/`, `TAS/`, `RBC/`, etc.) are ignored
- `api_keys.txt`, `uploads/`, `output/`, `build/`, `dist/` are ignored
- **Processor `.py` files inside `processors/` ARE tracked** (they are code, not data)

## Coding Conventions

- Processors output `.xlsx` via `openpyxl` with styled headers (fill `1F4E78`, white bold font)
- `job.progress` goes from 0→100; update `job.message` at each major step
- Standalone scripts (in broker folders like `RBC/News from nashville/script.py`) can exist alongside processors for CLI usage
- Commit messages: `feat:`, `fix:`, `chore:` prefixes

## SSL / Zscaler

`custom_bundle.pem` is bundled for corporate proxy. `app.py` sets `REQUESTS_CA_BUNDLE` and `SSL_CERT_FILE` env vars at startup.

## Deploy Steps

```bash
git add -A
git commit -m "feat: description"
git push origin main
git push hf main
```
