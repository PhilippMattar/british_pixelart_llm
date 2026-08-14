#!/bin/bash -eu
# Real QLoRA training (PLAN.md §7.2): committed data -> adapter -> GGUF, per persona.
# Generalises g1.sbatch (same container/mount pattern, proven by the G1 gate). Trains each
# requested persona in turn, then converts its adapter to a GGUF ready for `ollama create`.
# Submit via training/submit_train.sh (it supplies -A/-p/-C and BPX_PERSONA). Runs fully
# offline: env/setup_env.sh + download_weights.py must have run first.
# -A / -p / -C come from submit_train.sh (#SBATCH can't expand variables).
#SBATCH --job-name=bpx-train
#SBATCH --nodes=1
#SBATCH --gpus=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64gb
# Two personas at ~30-60 min each (§7.2) + the ~15 min container import. Generous headroom;
# gpu-batch allows 7d, so no reason to cut it fine.
#SBATCH --time=03:00:00
#SBATCH --output=bpx-train_%j.log

# Slurm executes a SPOOLED COPY of this file, so $0 can't locate the repo — submit_train.sh
# passes the real path in BPX_TRAINING_DIR instead.
REPO="${BPX_TRAINING_DIR:?not set — submit via 'bash training/submit_train.sh', not sbatch directly}"
source "$REPO/config.sh"
mkdir -p "$BPX_WORK_DIR"

# Which persona(s): BPX_PERSONA = british | scottish | both (default both).
case "${BPX_PERSONA:-both}" in
  both) PERSONAS="british scottish" ;;
  *)    PERSONAS="${BPX_PERSONA}" ;;
esac

# Optional hyperparameter overrides forwarded to train_qlora.py (else its §7.2 defaults apply).
EXTRA=""
if [ -n "${BPX_TRAIN_EPOCHS:-}" ]; then EXTRA="$EXTRA --epochs $BPX_TRAIN_EPOCHS"; fi
if [ -n "${BPX_TRAIN_LR:-}" ];     then EXTRA="$EXTRA --lr $BPX_TRAIN_LR"; fi
if [ -n "${BPX_TRAIN_LOSS:-}" ];   then EXTRA="$EXTRA --loss $BPX_TRAIN_LOSS"; fi
echo "[train] personas: $PERSONAS | extra args:$EXTRA"

srun --container-image="$BPX_SQSH" \
     --container-mounts="$BPX_PROJECT_DIR:$BPX_PROJECT_DIR" \
     --container-workdir="$REPO" \
     bash -c "set -euo pipefail
       source config.sh
       source \"\$BPX_VENV/bin/activate\"   # must precede any python use (see env/setup_env.sh)
       export HF_HUB_OFFLINE=1
       for P in $PERSONAS; do
         echo \"=== [train] \$P ===\"
         python train_qlora.py --base \"\$BPX_BASE_DIR\" \
                               --data \"data/\${P}_train.jsonl\" \
                               --val  \"data/\${P}_val.jsonl\" \
                               --out  \"\$BPX_WORK_DIR/\${P}-adapter\" $EXTRA
         bash export_gguf.sh \"\$BPX_WORK_DIR/\${P}-adapter\" \"\$BPX_WORK_DIR/\${P}.gguf\"
       done"

echo "[train] done. adapters + gguf in $BPX_WORK_DIR/{british,scottish}.gguf"
echo "[train] next (locally): rsync the .gguf files to models/adapters/ then ollama create"
echo "        (see models/README.md); eval with training/eval.py before wiring models.toml."
