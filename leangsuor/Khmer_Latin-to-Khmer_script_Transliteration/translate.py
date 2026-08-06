"""
Interactive transliteration — test your own romanization input.

Usage
-----
    python translate.py
    python translate.py --gru    hf_models/gru_v3_bs64_ed128_ld512
    python translate.py --lstm   hf_models/lstm_v3_bs32_ed64_ld512
    python translate.py --fuzzy  hf_models/fuzzy_ngram_greedy_backoff
    python translate.py --text "soksabay"
"""

import argparse
import pickle
import sys
from pathlib import Path

import tensorflow as tf
# Force CPU — Metal/CUDA floating-point differences cause the decoder to never
# emit the EOS token, producing infinite garbage output.
tf.config.set_visible_devices([], "GPU")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

DEFAULT_GRU   = "hf_models/gru_v3_bs64_ed128_ld512"
DEFAULT_LSTM  = "hf_models/lstm_v3_bs32_ed64_ld512"
DEFAULT_FUZZY = "hf_models/fuzzy_ngram_greedy_backoff"


def load_models(gru_path, lstm_path, fuzzy_path):
    models = {}

    if gru_path and Path(gru_path).exists():
        print(f"Loading GRU  : {gru_path}")
        from models.seq2seq_gru_transliteration import Seq2SeqGRUTransliterator
        models["GRU"] = Seq2SeqGRUTransliterator(gru_path).transliterate_sentence
        print("  ✓ GRU loaded")

    if lstm_path and Path(lstm_path).exists():
        print(f"Loading LSTM : {lstm_path}")
        from models.seq2seq_lstm_transliteration import Seq2SeqTransliterator
        models["LSTM"] = Seq2SeqTransliterator(lstm_path).transliterate_sentence
        print("  ✓ LSTM loaded")

    if fuzzy_path and Path(fuzzy_path).exists():
        pkl = Path(fuzzy_path) / "checkpoints" / "model.pkl"
        if pkl.exists():
            print(f"Loading Fuzzy: {fuzzy_path}")
            with open(pkl, "rb") as f:
                predictor = pickle.load(f)
            models["Fuzzy"] = lambda s: " ".join(predictor.translate_with_beam_search(s))
            print("  ✓ Fuzzy loaded")

    return models


def normalize(text: str) -> str:
    import re
    return re.sub(r'(.)\1{2,}', r'\1\1', text)


def translate_all(models, text):
    normalized = normalize(text)
    print(f"\n  Input  : {text}")
    if normalized != text:
        print(f"  Normalized: {normalized}")
    print(f"  {'─'*50}")
    for name, fn in models.items():
        result = fn(normalized)
        print(f"  {name:<6} : {result}")
    print()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gru",   default=DEFAULT_GRU,   help="GRU model directory")
    parser.add_argument("--lstm",  default=DEFAULT_LSTM,  help="LSTM model directory")
    parser.add_argument("--fuzzy", default=DEFAULT_FUZZY, help="Fuzzy model directory")
    parser.add_argument("--text",  default=None,          help="Single input to translate (non-interactive)")
    args = parser.parse_args()

    print("\nLoading models...")
    models = load_models(args.gru, args.lstm, args.fuzzy)

    if not models:
        print("No models found. Check your paths.")
        sys.exit(1)

    print(f"\nLoaded: {list(models.keys())}")

    if args.text:
        translate_all(models, args.text)
        return

    print("\nType a romanization and press Enter. Type 'quit' to exit.\n")
    while True:
        try:
            text = input("Roman > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break
        if not text:
            continue
        if text.lower() in ("quit", "exit", "q"):
            print("Bye!")
            break
        translate_all(models, text)


if __name__ == "__main__":
    main()
