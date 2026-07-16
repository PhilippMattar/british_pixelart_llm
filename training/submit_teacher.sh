#!/usr/bin/env bash
# Submit the teacher-generation job. Supplies -A/-p/-C + the repo path (sbatch spools the script).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/config.sh"

[ -f "$BPX_SQSH" ] || { echo "Missing $BPX_SQSH — run 'bash training/env/import_image.sh' first." >&2; exit 1; }
[ -d "$BPX_TEACHER_DIR" ] || { echo "Missing teacher at $BPX_TEACHER_DIR — run 'python training/download_teacher.py' first." >&2; exit 1; }

sbatch -A "$BPX_ACCOUNT" \
       -p "$BPX_PARTITION_BATCH" \
       -C "$BPX_TEACHER_CONSTRAINT" \
       --export=ALL,BPX_TRAINING_DIR="$HERE" \
       "$HERE/slurm/teacher.sbatch"
echo "[submit] teacher gen queued on $BPX_PARTITION_BATCH ($BPX_TEACHER_CONSTRAINT)"
echo "[submit] watch: squeue --me   /   tail -f bpx-teacher_*.log"
