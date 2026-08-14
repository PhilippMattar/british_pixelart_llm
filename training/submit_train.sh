#!/usr/bin/env bash
# Submit the real QLoRA training job (PLAN.md §7.2). Supplies -A/-p/-C from config.sh (which
# can't use vars in #SBATCH) and forwards the persona + optional hyperparameter knobs.
#
#   bash training/submit_train.sh                 # train both personas (default)
#   BPX_PERSONA=scottish bash training/submit_train.sh   # just one
#   BPX_TRAIN_EPOCHS=2 BPX_TRAIN_LOSS=full bash training/submit_train.sh   # override defaults
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/config.sh"

# Must be a *-batch partition: gpu-shortrun/gpu-interactive reject sbatch (srun/salloc only).
# BPX_TRAINING_DIR: Slurm runs a *spooled copy* of the batch script, so the job can't find the
# repo from $0. We know the real path here, so pass it (plus the forwarded BPX_* knobs) along.
sbatch -A "$BPX_ACCOUNT" \
       -p "$BPX_PARTITION_BATCH" \
       -C "$BPX_GPU_CONSTRAINT" \
       --export=ALL,BPX_TRAINING_DIR="$HERE",BPX_PERSONA="${BPX_PERSONA:-both}",BPX_TRAIN_EPOCHS="${BPX_TRAIN_EPOCHS:-}",BPX_TRAIN_LR="${BPX_TRAIN_LR:-}",BPX_TRAIN_LOSS="${BPX_TRAIN_LOSS:-}" \
       "$HERE/slurm/train.sbatch"
echo "[submit] queued on $BPX_PARTITION_BATCH ($BPX_GPU_CONSTRAINT), persona=${BPX_PERSONA:-both}"
echo "[submit] watch with: squeue --me   /   tail -f bpx-train_*.log"
