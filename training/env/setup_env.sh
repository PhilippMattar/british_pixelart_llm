#!/usr/bin/env bash
# One-time environment build. Run on an interactive GPU node (which has internet):
#   bash training/env/setup_env.sh
# Creates a venv on the shared FS that inherits the container's torch, installs the training
# deps, and clones llama.cpp for GGUF export. Every batch job then reuses it fully offline.
set -euo pipefail

# Run this from the LOGIN node. It submits its own srun, so wrapping it in another srun
# deadlocks: the outer step holds the allocation and the inner one waits for it forever
# ("step creation temporarily disabled ... Requested nodes are busy").
if [ -n "${SLURM_JOB_ID:-}" ]; then
  echo "Don't wrap this in srun — it submits its own job. Run it plainly on the login node." >&2
  echo "(You are inside Slurm job ${SLURM_JOB_ID}.)" >&2
  exit 1
fi

HERE="$(cd "$(dirname "$0")/.." && pwd)"   # training/
source "$HERE/config.sh"

if [ ! -f "$BPX_SQSH" ]; then
  echo "Missing $BPX_SQSH — run 'bash training/env/import_image.sh' first." >&2
  exit 1
fi
mkdir -p "$BPX_PROJECT_DIR"

# Build the venv inside the container (so its interpreter/torch match run time).
# NOTE: --mem/-c are NOT optional. Pyxis imports the image by unpacking ~60 layers and
# running enroot-mksquashovlfs, which is host-RAM hungry — the default allocation gets
# OOM-killed (exit 137) before you ever reach a shell.
srun -A "$BPX_ACCOUNT" -p "$BPX_PARTITION_INTERACTIVE" -N 1 --gpus=1 \
  -C "$BPX_GPU_CONSTRAINT" -c 8 --mem=64G --time=01:00:00 \
  --container-image="$BPX_SQSH" \
  --container-mounts="$BPX_PROJECT_DIR:$BPX_PROJECT_DIR" \
  --container-workdir="$HERE" \
  bash -c '
    set -euo pipefail
    source config.sh
    # NOTE: `bash -c`, NOT `bash -lc`. Enroot mounts $HOME, so a login/interactive shell
    # sources ~/.bashrc, activates your conda base, and shadows the container python — the
    # venv would then inherit conda (no torch) instead of the container. Fail fast if the
    # python we are about to build on is not the container one.
    echo "[setup] python: $(command -v python)"
    python -c "import torch; print(\"[setup] container torch:\", torch.__version__)"
    python -m venv --system-site-packages "$BPX_VENV"   # inherit the container torch
    source "$BPX_VENV/bin/activate"
    pip install --no-cache-dir -U pip
    pip install --no-cache-dir -r env/requirements.txt
    python -c "import torch, transformers, peft, trl, bitsandbytes, gguf; print(\"train deps OK\")"
  '

# llama.cpp clone happens on the login node (has internet), not in the offline batch job.
if [ ! -d "$LLAMA_CPP" ]; then
  git clone --depth 1 https://github.com/ggml-org/llama.cpp "$LLAMA_CPP"
fi

echo "[setup] venv=$BPX_VENV"
echo "[setup] llama.cpp=$LLAMA_CPP"
echo "[setup] next: python training/download_weights.py   (on the login node)"
