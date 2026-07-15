#!/usr/bin/env bash
# Submit the G1 gate job. Supplies -A/-p from config.sh (which can't use vars in #SBATCH).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/config.sh"

sbatch -A "$BPX_ACCOUNT" \
       -p "$BPX_PARTITION_SHORT" \
       -C "$BPX_GPU_CONSTRAINT" \
       "$HERE/slurm/g1.sbatch"
echo "[submit] queued on $BPX_PARTITION_SHORT ($BPX_GPU_CONSTRAINT)"
echo "[submit] watch with: squeue --me   /   tail -f bpx-g1_*.log"
