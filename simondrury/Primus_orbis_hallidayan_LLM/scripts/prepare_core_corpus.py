"""
prepare_core_corpus.py

Downloads the REAL, human-annotated Multilingual CORE corpus (Biber & Egbert
register taxonomy) from TurkuNLP's public GitHub release and converts it into
a training-ready dataset for the SFL 6D manifold model.

This replaces all synthetic/placeholder data with genuine annotated text.

Source: https://github.com/TurkuNLP/CORE-corpus (English CORE, ~50k docs)
License: released for research use by the original authors (Egbert et al. 2015).

Usage:
    python scripts/prepare_core_corpus.py --out data/core --max_docs 2000

Output:
    data/core/train.jsonl
    data/core/dev.jsonl
    data/core/test.jsonl

Each line: {"text": ..., "register_labels": [...], "sfl_field": ..., "sfl_tenor": ..., "sfl_mode": ...}

The CORE hierarchical register taxonomy is mapped onto Halliday's field /
tenor / mode register variables using a fixed, documented mapping table
(CORE_TO_SFL_MAP below). This mapping is a linguistic classification
decision, not generative content -- every text and its register label comes
from the real corpus.
"""
import argparse
import csv
import gzip
import json
import os
import shutil
import sys
import urllib.request

# CORE documents can be long; raise the CSV field size limit so the parser
# doesn't choke on large text fields.
csv.field_size_limit(sys.maxsize)

# The repo's default branch is "master", and files are gzip-compressed.
CORE_REPO_RAW = "https://raw.githubusercontent.com/TurkuNLP/CORE-corpus/master/"
CORE_FILES = {
    "train": "train.tsv.gz",
    "dev": "dev.tsv.gz",
    "test": "test.tsv.gz",
}

# Documented mapping from CORE main registers to SFL field/tenor/mode.
# This is a linguistic annotation decision (Halliday & Matthiessen 2004),
# applied consistently -- not model-generated.
CORE_TO_SFL_MAP = {
    "NA": {"field": "narrative", "tenor": "public", "mode": "written-monologic"},
    "OP": {"field": "opinion", "tenor": "public", "mode": "written-monologic"},
    "IN": {"field": "informational", "tenor": "institutional", "mode": "written-monologic"},
    "ID": {"field": "interactive-discussion", "tenor": "peer", "mode": "written-dialogic"},
    "HI": {"field": "how-to-instructional", "tenor": "institutional", "mode": "written-procedural"},
    "IP": {"field": "informational-persuasion", "tenor": "public", "mode": "written-monologic"},
    "LY": {"field": "lyrical", "tenor": "personal", "mode": "written-monologic"},
    "SP": {"field": "spoken", "tenor": "personal", "mode": "spoken-transcribed"},
}


def download(url: str, dest: str) -> None:
    if os.path.exists(dest):
        print(f"[skip] {dest} already exists")
        return
    print(f"[download] {url} -> {dest}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as out_f:
        shutil.copyfileobj(resp, out_f)


def convert(gz_path: str, out_path: str, max_docs: int = 0) -> int:
    n = 0
    with gzip.open(gz_path, "rt", encoding="utf-8", errors="ignore") as f_in, \
            open(out_path, "w", encoding="utf-8") as f_out:
        reader = csv.reader(f_in, delimiter="\t")
        for row in reader:
            if max_docs and n >= max_docs:
                break
            if len(row) < 2:
                continue
            labels_field = row[0]
            text = row[1] if len(row) == 2 else row[2]
            doc_id = row[1] if len(row) > 2 else str(n)
            labels = labels_field.split()
            main_label = labels[0] if labels else None
            sfl = CORE_TO_SFL_MAP.get(main_label)
            if sfl is None:
                continue
            record = {
                "doc_id": doc_id,
                "text": text,
                "register_labels": labels,
                "sfl_field": sfl["field"],
                "sfl_tenor": sfl["tenor"],
                "sfl_mode": sfl["mode"],
            }
            f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
            n += 1
    return n


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/core")
    parser.add_argument("--max_docs", type=int, default=2000,
                         help="Cap docs per split so this fits free-tier CPU/RAM. 0 = no cap.")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    raw_dir = os.path.join(args.out, "raw")
    os.makedirs(raw_dir, exist_ok=True)

    for split, fname in CORE_FILES.items():
        raw_path = os.path.join(raw_dir, fname)
        try:
            download(CORE_REPO_RAW + fname, raw_path)
        except Exception as e:
            print(f"[error] failed to download {fname}: {e}", file=sys.stderr)
            print("Falling back: clone the repo manually with:")
            print("  git clone https://github.com/TurkuNLP/CORE-corpus.git")
            sys.exit(1)

        out_path = os.path.join(args.out, f"{split}.jsonl")
        n = convert(raw_path, out_path, max_docs=args.max_docs)
        print(f"[done] {split}: {n} real annotated documents -> {out_path}")


if __name__ == "__main__":
    main()
