import json
import logging
import argparse
import time
from collections import Counter
from typing import List, Dict, Any
from pathlib import Path
from dotenv import load_dotenv

from src.processing.language_detector import LanguageDetector
from src.processing.pii_scrubber import PIIScrubber
from src.processing.relevance_filter import RelevanceFilter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("run_phase2")

def load_jsonl(filepath: str) -> List[Dict[str, Any]]:
    records = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records

def save_jsonl(records: List[Dict[str, Any]], filepath: str):
    with open(filepath, 'w', encoding='utf-8') as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')

def main():
    parser = argparse.ArgumentParser(description="Phase 2: Processing and Deep Cleaning")
    parser.add_argument("--mode", type=str, default="smoke", choices=["smoke", "full", "retry-exhausted"], help="Run mode")
    parser.add_argument("--input", type=str, default="data/output/reviews_raw.jsonl", help="Input file")
    parser.add_argument("--output", type=str, default="data/output/reviews_clean.jsonl", help="Output file")
    parser.add_argument("--meta", type=str, default="data/output/phase2_meta.json", help="Meta file")
    args = parser.parse_args()

    load_dotenv()

    logger.info(f"Starting Phase 2 Processing | mode={args.mode}")
    
    if args.mode == "retry-exhausted":
        # In retry mode, the input is already the output of a previous run
        input_path = Path(args.output)
    else:
        input_path = Path(args.input)
        
    if not input_path.exists():
        logger.error(f"Input file {input_path} not found.")
        return

    records = load_jsonl(input_path)
    logger.info(f"Loaded {len(records)} records from {input_path}")

    if args.mode == "smoke":
        records = records[:50]
        logger.info(f"Smoke mode: truncating to 50 records.")

    detector = LanguageDetector()
    scrubber = PIIScrubber()
    try:
        filterer = RelevanceFilter()
    except ValueError as e:
        logger.error(str(e))
        logger.error("Cannot proceed without GROQ_API_KEY")
        return

    # Track stats
    lang_counts = Counter()
    rel_counts = Counter()
    status_counts = Counter()
    source_rel_counts = Counter()

    if args.mode != "retry-exhausted":
        # Pass 1: Language and PII
        logger.info("Running Language Detection & PII Scrubbing...")
        for rec in records:
            text = rec.get("text", "")
            scrubbed = scrubber.scrub(text)
            rec["text"] = scrubbed
            
            lang = detector.detect_language(scrubbed)
            rec["lang"] = lang

    # Prepare for Pass 2
    if args.mode == "retry-exhausted":
        # Only process records marked as quota_exhausted
        to_process = [r for r in records if r.get("relevance_status") == "quota_exhausted"]
        logger.info(f"Found {len(to_process)} quota_exhausted records to retry.")
        if not to_process:
            logger.info("Nothing to retry. Exiting.")
            return
    else:
        to_process = records

    # Pass 2: Relevance Filter (Batch)
    logger.info(f"Running Relevance Filtering via Groq API (batch size {filterer.batch_size})...")
    
    batch_size = filterer.batch_size
    start_time = time.time()
    
    for i in range(0, len(to_process), batch_size):
        batch = to_process[i:i+batch_size]
        logger.info(f"Processing batch {i//batch_size + 1}/{(len(to_process) + batch_size - 1)//batch_size}")
        # Modifies records in-place
        filterer.process_batch(batch)
        
    duration = time.time() - start_time

    # Calculate final stats across ALL records
    for rec in records:
        lang_counts[rec.get("lang", "unknown")] += 1
        
        status = rec.get("relevance_status", "unknown")
        status_counts[status] += 1
        
        if status == "classified":
            rel = rec.get("relevant", False)
            source = rec.get("source", "unknown")
            rel_counts[rel] += 1
            source_rel_counts[f"{source}_{rel}"] += 1

    # Write output
    save_jsonl(records, args.output)
    logger.info(f"Saved {len(records)} records to {args.output}")

    # Build and write meta
    meta = {
        "processed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": args.mode,
        "total_processed": len(records),
        "language_distribution": dict(lang_counts),
        "relevance_status_distribution": dict(status_counts),
        "relevance_distribution": {
            "relevant": rel_counts.get(True, 0),
            "irrelevant": rel_counts.get(False, 0)
        },
        "source_relevance_breakdown": dict(source_rel_counts),
        "duration_seconds": round(duration, 2)
    }

    with open(args.meta, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2)
        
    logger.info(f"Saved meta to {args.meta}")
    logger.info("Phase 2 Complete.")

if __name__ == "__main__":
    main()
