#!/usr/bin/env bash
# Submit the G1 gate job. Supplies -A/-p from config.sh (which can't use vars in #SBATCH).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/config.sh"

if [ "$BPX_ACCOUNT" = "TODO_your_slurm_account" ]; then
  echo "Edit training/config.sh first: set BPX_ACCOUNT and BPX_PROJECT_DIR." >&2
  exit 1
fi

sbatch -A "$BPX_ACCOUNT" -p "$BPX_PARTITION_SHORT" "$HERE/slurm/g1.sbatch"
echo "[submit] queued on $BPX_PARTITION_SHORT — watch with: squeue --me   /   tail -f bpx-g1_*.log"
