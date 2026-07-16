#!/usr/bin/env bash
# ONE-TIME: import the vLLM container to a squashfs. Separate from the training image because
# vLLM pins its own torch (conflicts with the NGC image). Run on a RUN node. Idempotent.
set -euo pipefail

if [ -n "${SLURM_JOB_ID:-}" ]; then
  echo "Don't wrap this in srun — it submits its own job. Run it plainly on a run node." >&2
  exit 1
fi

HERE="$(cd "$(dirname "$0")/.." && pwd)"   # training/
source "$HERE/config.sh"

if [ -f "$BPX_VLLM_SQSH" ]; then
  echo "[import] already present: $BPX_VLLM_SQSH"
  ls -lh "$BPX_VLLM_SQSH"
  exit 0
fi
mkdir -p "$(dirname "$BPX_VLLM_SQSH")"

echo "[import] $BPX_VLLM_IMAGE_URI -> $BPX_VLLM_SQSH  (~10-20 min, once)"
srun -A "$BPX_ACCOUNT" -p "$BPX_PARTITION_CPU" -N 1 -c 8 --mem=64G --time=01:30:00 \
  bash -c "enroot import -o '$BPX_VLLM_SQSH' 'docker://$BPX_VLLM_IMAGE_URI'"

ls -lh "$BPX_VLLM_SQSH"
echo "[import] done — teacher.sbatch mounts this directly"
