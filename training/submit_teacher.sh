#!/usr/bin/env bash
# Submit the teacher-generation job. Supplies -A/-p/-C + the repo path (sbatch spools the script)
# and forwards the BPX_GEN_* knobs. Env overrides:
#   BPX_GEN_N       cap prompts per persona (0 = all)          default 0
#   BPX_GEN_BATCH   generation batch size                      default = generate.py's (4)
#   BPX_GEN_TIME    wall-clock limit                           default 00:45:00
#   BPX_GEN_OUT     output dir                                 default $BPX_WORK_DIR/spike
#   BPX_GEN_PROMPTS prompt bank jsonl; unset => the built bank if present, else the spike set
#
#   validation:  BPX_GEN_N=30 bash training/submit_teacher.sh
#   full run:    BPX_GEN_N=2500 BPX_GEN_BATCH=16 BPX_GEN_TIME=06:00:00 \
#                BPX_GEN_OUT="$BPX_WORK_DIR/gen" bash training/submit_teacher.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/config.sh"

[ -f "$BPX_SQSH" ] || { echo "Missing $BPX_SQSH — run 'bash training/env/import_image.sh' first." >&2; exit 1; }
[ -d "$BPX_TEACHER_DIR" ] || { echo "Missing teacher at $BPX_TEACHER_DIR — run 'python training/download_teacher.py' first." >&2; exit 1; }

# Default the prompt source to the built bank when present. Set BPX_GEN_PROMPTS="" to force the
# in-repo spike set; set it to a path to use a specific bank.
PROMPTS="${BPX_GEN_PROMPTS-__unset__}"
if [ "$PROMPTS" = "__unset__" ]; then
  if [ -f "$BPX_BANK" ]; then PROMPTS="$BPX_BANK"; else PROMPTS=""; fi
fi
TIME="${BPX_GEN_TIME:-00:45:00}"

sbatch -A "$BPX_ACCOUNT" \
       -p "$BPX_PARTITION_BATCH" \
       -C "$BPX_TEACHER_CONSTRAINT" \
       -t "$TIME" \
       --export=ALL,BPX_TRAINING_DIR="$HERE",BPX_GEN_PROMPTS="$PROMPTS",BPX_GEN_N="${BPX_GEN_N:-0}",BPX_GEN_BATCH="${BPX_GEN_BATCH:-}",BPX_GEN_OUT="${BPX_GEN_OUT:-}" \
       "$HERE/slurm/teacher.sbatch"
echo "[submit] queued on $BPX_PARTITION_BATCH ($BPX_TEACHER_CONSTRAINT), time=$TIME"
echo "[submit] prompts=${PROMPTS:-<spike set>}  n=${BPX_GEN_N:-0}  batch=${BPX_GEN_BATCH:-default}  out=${BPX_GEN_OUT:-$BPX_WORK_DIR/spike}"
echo "[submit] watch: squeue --me   /   tail -f bpx-teacher_*.log"
