"""Corpus schema validator — python3 data/validate.py
Checks every line of samples.jsonl: required fields, allowed values,
unique ids, class/language counts. Exits non-zero on any violation."""
import json
import sys
from collections import Counter
from pathlib import Path

PATH = Path(__file__).parent / "samples.jsonl"
LABELS = {"scam", "benign"}
TYPES = {"digital_arrest", "kyc_bank", "parcel_courier", "utility", "investment_task",
         "upi_request", "phishing_link", "impersonation", "none"}
LANGS = {"en", "hi", "hinglish", "bn", "ta", "te", "mr"}
REQUIRED = {"id", "text", "label", "scam_type", "language", "source", "synthetic"}

rows, errs, ids = [], [], set()
for i, line in enumerate(PATH.read_text(encoding="utf-8").splitlines(), 1):
    if not line.strip():
        continue
    try:
        r = json.loads(line)
    except json.JSONDecodeError as e:
        errs.append(f"line {i}: invalid JSON ({e})")
        continue
    missing = REQUIRED - r.keys()
    if missing:
        errs.append(f"line {i} ({r.get('id','?')}): missing {missing}")
    if r.get("label") not in LABELS:
        errs.append(f"{r.get('id')}: bad label {r.get('label')}")
    if r.get("scam_type") not in TYPES:
        errs.append(f"{r.get('id')}: bad scam_type {r.get('scam_type')}")
    if r.get("language") not in LANGS:
        errs.append(f"{r.get('id')}: bad language {r.get('language')}")
    if r.get("label") == "scam" and r.get("scam_type") == "none":
        errs.append(f"{r.get('id')}: scam with scam_type none")
    if r.get("label") == "benign" and r.get("scam_type") != "none":
        errs.append(f"{r.get('id')}: benign with scam_type {r.get('scam_type')}")
    if not isinstance(r.get("synthetic"), bool):
        errs.append(f"{r.get('id')}: synthetic must be boolean")
    if len(r.get("text", "")) < 15:
        errs.append(f"{r.get('id')}: text too short")
    if r.get("id") in ids:
        errs.append(f"duplicate id {r.get('id')}")
    ids.add(r.get("id"))
    rows.append(r)

by_label = Counter(r["label"] for r in rows)
by_type = Counter(r["scam_type"] for r in rows if r["label"] == "scam")
by_lang = Counter(r["language"] for r in rows)
verbatim = sum(1 for r in rows if not r["synthetic"])

print(f"samples: {len(rows)}  scam: {by_label['scam']}  benign: {by_label['benign']}  verbatim-derived: {verbatim}")
print("classes:", dict(sorted(by_type.items())))
print("languages:", dict(sorted(by_lang.items())))
if errs:
    print(f"\n{len(errs)} ERRORS:")
    for e in errs:
        print(" -", e)
    sys.exit(1)
print("VALID — corpus schema clean")
