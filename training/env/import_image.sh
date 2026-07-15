#!/usr/bin/env bash
# ONE-TIME: import the container image into a squashfs on the shared FS.
#   bash training/env/import_image.sh
#
# Why: letting pyxis pull nvcr.io per job costs ~15 min of RUNTIME every time (60 layers,
# ~20GB, unpack + mksquashfs) — we measured a job get killed by a 15-min limit purely on the
# import. Importing once to $BPX_SQSH turns that into a mount that starts in seconds.
# Idempotent: does nothing if the squashfs already exists.
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"   # training/
source "$HERE/config.sh"

if [ -f "$BPX_SQSH" ]; then
  echo "[import] already present: $BPX_SQSH"
  ls -lh "$BPX_SQSH"
  exit 0
fi
mkdir -p "$(dirname "$BPX_SQSH")"

# enroot import is CPU+RAM heavy (unpack + mksquashfs) but needs NO GPU, so use a cpu node.
# If enroot isn't on the cpu nodes, rerun with: BPX_PARTITION_CPU=gpu-interactive
echo "[import] $BPX_IMAGE_URI -> $BPX_SQSH  (this is the slow part; ~15-20 min, once)"
srun -A "$BPX_ACCOUNT" -p "$BPX_PARTITION_CPU" -N 1 -c 8 --mem=64G --time=01:30:00 \
  bash -c "command -v enroot >/dev/null || { echo 'enroot not on this partition; retry with BPX_PARTITION_CPU=gpu-interactive' >&2; exit 1; }
           enroot import -o '$BPX_SQSH' 'docker://$BPX_IMAGE_URI'"

ls -lh "$BPX_SQSH"
echo "[import] done — every job now mounts this directly, no registry pull"
