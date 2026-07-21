#!/bin/bash -eu
# Teacher generation (PLAN.md §6.2/§6.3): the teacher answers the prompts in persona
# (transformers, in the NGC container we use for training — the vLLM OCI image won't import via
# the cluster's enroot). Submit via training/submit_teacher.sh, which passes the BPX_GEN_* knobs.
# Runs offline: download_teacher.py must have run first.
#SBATCH --job-name=bpx-teacher
#SBATCH --nodes=1
#SBATCH --gpus=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=96gb
#SBATCH --time=00:45:00
#SBATCH --output=bpx-teacher_%j.log

REPO="${BPX_TRAINING_DIR:?not set — submit via 'bash training/submit_teacher.sh'}"
source "$REPO/config.sh"

OUT="${BPX_GEN_OUT:-$BPX_WORK_DIR/spike}"
mkdir -p "$OUT"

# Assemble generate.py args here (the batch node has the BPX_GEN_* overrides from submit).
# Paths on this cluster have no spaces, so word-splitting into the container command is safe.
GEN_ARGS="--model $BPX_TEACHER_DIR --out-dir $OUT"
if [ -n "${BPX_GEN_PROMPTS:-}" ]; then GEN_ARGS="$GEN_ARGS --prompts $BPX_GEN_PROMPTS"; fi
if [ "${BPX_GEN_N:-0}" -gt 0 ];   then GEN_ARGS="$GEN_ARGS --n $BPX_GEN_N"; fi
if [ -n "${BPX_GEN_BATCH:-}" ];   then GEN_ARGS="$GEN_ARGS --batch-size $BPX_GEN_BATCH"; fi
echo "[teacher] generate.py $GEN_ARGS"

srun --container-image="$BPX_SQSH" \
     --container-mounts="$BPX_PROJECT_DIR:$BPX_PROJECT_DIR" \
     --container-workdir="$REPO" \
     bash -c "set -euo pipefail
       source config.sh
       source \"\$BPX_VENV/bin/activate\"
       export HF_HUB_OFFLINE=1
       python generate.py $GEN_ARGS"

echo "[teacher] done -> $OUT/{british,scottish}.jsonl"
