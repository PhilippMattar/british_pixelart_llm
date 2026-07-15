#!/usr/bin/env bash
# One-time environment build. Run on an interactive GPU node (which has internet):
#   bash training/env/setup_env.sh
# Creates a venv on the shared FS that inherits the container's torch, installs the training
# deps, and clones llama.cpp for GGUF export. Every batch job then reuses it fully offline.
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"   # training/
source "$HERE/config.sh"

mkdir -p "$BPX_PROJECT_DIR"

# Build the venv inside the container (so its interpreter/torch match run time).
# NOTE: --mem/-c are NOT optional. Pyxis imports the image by unpacking ~60 layers and
# running enroot-mksquashovlfs, which is host-RAM hungry — the default allocation gets
# OOM-killed (exit 137) before you ever reach a shell.
srun -A "$BPX_ACCOUNT" -p "$BPX_PARTITION_INTERACTIVE" -N 1 --gpus=1 \
  -C "$BPX_GPU_CONSTRAINT" -c 8 --mem=64G --time=00:40:00 \
  --container-image="$BPX_IMAGE" \
  --container-mounts="$BPX_PROJECT_DIR:$BPX_PROJECT_DIR" \
  --container-workdir="$HERE" \
  bash -lc '
    set -euo pipefail
    source config.sh
    python -m venv --system-site-packages "$BPX_VENV"   # inherit the container torch
    source "$BPX_VENV/bin/activate"
    pip install --no-cache-dir -U pip
    pip install --no-cache-dir -r env/requirements.txt
    python -c "import transformers, peft, trl, bitsandbytes, gguf; print(\"train deps OK\")"
  '

# llama.cpp clone happens on the login node (has internet), not in the offline batch job.
if [ ! -d "$LLAMA_CPP" ]; then
  git clone --depth 1 https://github.com/ggml-org/llama.cpp "$LLAMA_CPP"
fi

echo "[setup] venv=$BPX_VENV"
echo "[setup] llama.cpp=$LLAMA_CPP"
echo "[setup] next: python training/download_weights.py   (on the login node)"
