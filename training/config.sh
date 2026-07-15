# Shared config for the Phase-2 training pipeline (HPI SCI HPC). `source` before running.
# Jobs run in Enroot/Pyxis containers on Slurm; see training/README.md.

# Slurm allocation for -A — the course allocation, NOT your login.
# Confirmed 2026-07-12 via: sacctmgr show assoc user=$USER format=account,user,partition
export BPX_ACCOUNT="${BPX_ACCOUNT:-sci-lippert-intelligent-agents}"
# Workspace for BIG artifacts (16GB base weights, venv, hf-cache, llama.cpp, adapters).
# MUST NOT be your git checkout, or those land inside the repo. $HOME is on the shared FS
# and visible from every node (200GB quota — see training/README.md for the budget).
export BPX_PROJECT_DIR="${BPX_PROJECT_DIR:-$HOME/bpx-work}"

# Local-only: SSH target for copying results back to your laptop (NOT used by cluster jobs).
# Format: user@access-node. Reach it over the *Scientific Compute* VPN (not the HPI VPN).
export BPX_CLUSTER_SSH="${BPX_CLUSTER_SSH:-philipp.mattar@hpc.sci.hpi.de}"

# Partitions — verified with `sinfo` on 2026-07-12. Always set --time explicitly (default 8h).
export BPX_PARTITION_INTERACTIVE="${BPX_PARTITION_INTERACTIVE:-gpu-interactive}"  # 8h — probe / env build
export BPX_PARTITION_SHORT="${BPX_PARTITION_SHORT:-gpu-shortrun}"                 # 1d — G1 smoke job
export BPX_PARTITION_BATCH="${BPX_PARTITION_BATCH:-gpu-batch}"                    # 7d — real training / teacher gen
export BPX_PARTITION_CPU="${BPX_PARTITION_CPU:-cpu-interactive}"                  # 8h — image import (no GPU needed)

# GPU selection. g1_smoke.py trains in bf16, which needs Ampere+ (CC>=8.0), and our container
# is x86 — so pin A100. This rules out V100/2080Ti (no bf16) and GH200 (ARM, wrong arch), all
# of which sit in gpu-interactive. A100 40GB is ample for an 8B QLoRA.
# NOTE: the H100s exist ONLY in the aisc-* partitions, not the general gpu-* ones.
export BPX_GPU_CONSTRAINT="${BPX_GPU_CONSTRAINT:-GPU_SKU:A100}"

# Pyxis/Enroot container: NGC PyTorch has CUDA + torch prebuilt (x86; fine on A100).
# Pulling this from the registry costs ~15 MINUTES of job runtime *every time* (60 layers,
# ~20GB, unpack + mksquashfs). So env/import_image.sh imports it ONCE into a squashfs on the
# shared FS, and every job mounts that file instead (pyxis takes a path) — starts in seconds.
export BPX_IMAGE_URI="${BPX_IMAGE_URI:-nvcr.io#nvidia/pytorch:25.01-py3}"   # upstream; imported once
export BPX_SQSH="${BPX_SQSH:-$BPX_PROJECT_DIR/images/pytorch-25.01.sqsh}"   # what jobs actually mount

# Models
export BPX_BASE_HF="${BPX_BASE_HF:-Qwen/Qwen3-8B}"                  # unquantized student base (§3)
export BPX_OLLAMA_BASE_TAG="${BPX_OLLAMA_BASE_TAG:-qwen3:8b}"       # matching Ollama serve tag

# Derived paths on the shared FS (/sc/home or /sc/projects — visible on all nodes)
export BPX_BASE_DIR="$BPX_PROJECT_DIR/models/qwen3-8b"             # pre-staged base weights
export BPX_WORK_DIR="$BPX_PROJECT_DIR/work"                        # adapters, dummy data, gguf, logs
export BPX_VENV="$BPX_PROJECT_DIR/venv"                            # training deps (built by setup_env.sh)
export LLAMA_CPP="$BPX_PROJECT_DIR/llama.cpp"                      # for GGUF adapter conversion
export HF_HOME="$BPX_PROJECT_DIR/hf-cache"                         # HF cache on shared NVMe

# Big *transient* artifacts (the teacher weights + its HF cache during data-gen) go on scratch,
# NOT home, to protect the 200GB home quota. Global scratch is huge (~450TB) but ephemeral —
# fine for re-downloadable model weights. Used by the later teacher-generation stage.
export BPX_SCRATCH_DIR="${BPX_SCRATCH_DIR:-/sc/scratch/$USER/bpx}"
export BPX_TEACHER_HF="${BPX_TEACHER_HF:-Qwen/Qwen2.5-72B-Instruct-AWQ}"   # ~40GB, 1x H100 via vLLM
