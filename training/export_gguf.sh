#!/usr/bin/env bash
# Convert a trained PEFT LoRA adapter to a GGUF adapter with llama.cpp.
#   bash training/export_gguf.sh <adapter_dir> <out.gguf>
# Needs the llama.cpp clone from env/setup_env.sh (no network here).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/config.sh"

ADAPTER_DIR="${1:?usage: export_gguf.sh <adapter_dir> <out.gguf>}"
OUT="${2:?usage: export_gguf.sh <adapter_dir> <out.gguf>}"

if [ ! -d "$LLAMA_CPP" ]; then
  echo "llama.cpp missing at $LLAMA_CPP — run training/env/setup_env.sh first." >&2
  exit 1
fi

# Adapter GGUF is written against the base architecture. If flags differ in your llama.cpp
# version, check:  python "$LLAMA_CPP/convert_lora_to_gguf.py" --help
python "$LLAMA_CPP/convert_lora_to_gguf.py" \
  --base "$BPX_BASE_DIR" \
  --outfile "$OUT" \
  "$ADAPTER_DIR"

echo "[export] wrote $OUT"
