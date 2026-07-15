#!/bin/bash -eux
# G1 gate batch job (PLAN.md §7.1): dummy data -> QLoRA smoke -> GGUF adapter.
# Submit via training/submit_g1.sh (it supplies -A and -p from config.sh).
# Runs fully offline: env/setup_env.sh + download_weights.py must have run first.
# -A / -p / -C come from submit_g1.sh (#SBATCH can't expand variables).
#SBATCH --job-name=bpx-g1
#SBATCH --nodes=1
#SBATCH --gpus=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64gb
# Generous: the container import alone costs ~15 min (60 layers, ~20GB) before our code
# starts. gpu-shortrun allows 1 day, so there's no reason to cut this fine.
#SBATCH --time=01:30:00
#SBATCH --output=bpx-g1_%j.log

REPO="$(cd "$(dirname "$0")/.." && pwd)"   # training/
source "$REPO/config.sh"
mkdir -p "$BPX_WORK_DIR"

srun --container-image="$BPX_IMAGE" \
     --container-mounts="$BPX_PROJECT_DIR:$BPX_PROJECT_DIR" \
     --container-workdir="$REPO" \
     bash -c '
       set -euo pipefail
       source config.sh
       source "$BPX_VENV/bin/activate"   # must precede any python use (see env/setup_env.sh)
       export HF_HUB_OFFLINE=1
       python make_dummy_data.py --out "$BPX_WORK_DIR/g1_dummy.jsonl"
       python g1_smoke.py --base "$BPX_BASE_DIR" \
                          --data "$BPX_WORK_DIR/g1_dummy.jsonl" \
                          --out  "$BPX_WORK_DIR/g1-adapter"
       bash export_gguf.sh "$BPX_WORK_DIR/g1-adapter" "$BPX_WORK_DIR/g1.gguf"
     '

echo "[g1] done -> $BPX_WORK_DIR/g1.gguf"
echo "[g1] next (locally): rsync g1.gguf to models/adapters/ then ollama create (see models/README.md)"
