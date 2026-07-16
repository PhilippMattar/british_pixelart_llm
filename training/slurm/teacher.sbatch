#!/bin/bash -eux
# Teacher generation (PLAN.md §6.3): the teacher answers the prompts in persona (transformers,
# in the NGC container we use for training — the vLLM OCI image won't import via the cluster's
# enroot; vLLM is the later throughput path). Submit via training/submit_teacher.sh (supplies
# -A/-p/-C + BPX_TRAINING_DIR). Runs offline: download_teacher.py must have run first.
#SBATCH --job-name=bpx-teacher
#SBATCH --nodes=1
#SBATCH --gpus=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=96gb
#SBATCH --time=00:45:00
#SBATCH --output=bpx-teacher_%j.log

REPO="${BPX_TRAINING_DIR:?not set — submit via 'bash training/submit_teacher.sh'}"
source "$REPO/config.sh"
mkdir -p "$BPX_WORK_DIR/spike"

srun --container-image="$BPX_SQSH" \
     --container-mounts="$BPX_PROJECT_DIR:$BPX_PROJECT_DIR" \
     --container-workdir="$REPO" \
     bash -c '
       set -euo pipefail
       source config.sh
       source "$BPX_VENV/bin/activate"
       export HF_HUB_OFFLINE=1
       python generate.py --model "$BPX_TEACHER_DIR" --out-dir "$BPX_WORK_DIR/spike"
     '

echo "[teacher] done -> $BPX_WORK_DIR/spike/{british,scottish}.jsonl"
echo "[teacher] review: rsync them back and read them before scaling up"
