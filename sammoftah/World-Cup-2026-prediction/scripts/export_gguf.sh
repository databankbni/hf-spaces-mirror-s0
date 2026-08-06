#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <llama.cpp-dir> <merged-model-dir> <output.gguf>" >&2
  exit 2
fi

LLAMA_CPP_DIR="$1"
MODEL_DIR="$2"
OUTPUT="$3"
F16_OUTPUT="${OUTPUT%.gguf}.f16.gguf"

python3 "$LLAMA_CPP_DIR/convert_hf_to_gguf.py" \
  "$MODEL_DIR" \
  --outfile "$F16_OUTPUT" \
  --outtype f16

"$LLAMA_CPP_DIR/build/bin/llama-quantize" \
  "$F16_OUTPUT" \
  "$OUTPUT" \
  Q4_K_M

echo "Wrote $OUTPUT"
