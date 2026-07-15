#!/usr/bin/env bash
# Submit the G1 gate job. Supplies -A/-p from config.sh (which can't use vars in #SBATCH).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/config.sh"

# Must be a *-batch partition: gpu-shortrun/gpu-interactive reject sbatch (srun/salloc only).
sbatch -A "$BPX_ACCOUNT" \
       -p "$BPX_PARTITION_BATCH" \
       -C "$BPX_GPU_CONSTRAINT" \
       "$HERE/slurm/g1.sbatch"
echo "[submit] queued on $BPX_PARTITION_BATCH ($BPX_GPU_CONSTRAINT)"
echo "[submit] watch with: squeue --me   /   tail -f bpx-g1_*.log"
