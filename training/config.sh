# Shared config for the Phase-2 training pipeline (HPI SCI HPC). `source` before running.
# Jobs run in Enroot/Pyxis containers on Slurm; see training/README.md.

# Slurm allocation for -A — the course allocation, NOT your login.
# Confirmed 2026-07-12 via: sacctmgr show assoc user=$USER format=account,user,partition
export BPX_ACCOUNT="${BPX_ACCOUNT:-sci-lippert-intelligent-agents}"
# Workspace for BIG artifacts (~23GB container squashfs, ~16GB base weights, venv, llama.cpp,
# hf-cache, adapters, and later the teacher weights + datasets).
# MUST be OUTSIDE your git checkout (or they land in the repo) AND — strongly recommended —
# OUTSIDE home: home has a FIXED 200GB quota shared with everything, and HPI policy says
# project data belongs in a /sc/projects share (persistent, larger). Point it there via
# ~/.bashrc so it sticks, e.g.:
#   export BPX_PROJECT_DIR=/sc/projects/sci-lippert/intelligent-agents/$USER/bpx
# The $HOME default below is only a fallback for a quick first try.
export BPX_PROJECT_DIR="${BPX_PROJECT_DIR:-$HOME/bpx-work}"

# Local-only: SSH target for copying results back to your laptop (NOT used by cluster jobs).
# Use a RUN node (rx01/rx02) — file transfer is a listed use there, and the login node can
# block rsync's helper. Reach it over the *Scientific Compute* VPN (not the HPI VPN).
export BPX_CLUSTER_SSH="${BPX_CLUSTER_SSH:-philipp.mattar@rx01.hpc.sci.hpi.de}"

# Partitions — verified with `sinfo` + submission errors on the cluster. Always set --time.
# CRITICAL: partitions are split by SUBMISSION TYPE, not just duration. The *-interactive and
# gpu-shortrun partitions accept srun/salloc ONLY — sbatch is rejected ("Partition
# gpu-shortrun is interactive-only"). Anything sbatch'd must go to a *-batch partition.
export BPX_PARTITION_INTERACTIVE="${BPX_PARTITION_INTERACTIVE:-gpu-interactive}"  # 8h — srun only: probe / env build
export BPX_PARTITION_SHORT="${BPX_PARTITION_SHORT:-gpu-shortrun}"                 # 1d — srun only (NOT sbatch-able)
export BPX_PARTITION_BATCH="${BPX_PARTITION_BATCH:-gpu-batch}"                    # 7d — sbatch: G1 + real training
export BPX_PARTITION_CPU="${BPX_PARTITION_CPU:-cpu-interactive}"                  # 8h — srun only: image import

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

# Teacher for data generation (vLLM, so no llama.cpp/GGUF concern — the student's constraint
# doesn't apply here). Chosen 2026-07-16 after a web review: Qwen3.6-27B is the latest gen
# (Qwen3 -> 3.5 -> 3.6), *dense* (sources rate dense as best-for-creative-writing = humor),
# beats the older Qwen3.5-122B-A10B MoE overall, and stays Apache-2.0. Newer AND smaller than
# the previous Qwen2.5-72B-AWQ default. Serve it with a quant matched to the GPU at gen time:
#   Qwen/Qwen3.6-27B            bf16 ~54GB  -> A100 80GB (near-lossless)
#   Qwen/Qwen3.6-27B-FP8        ~27GB       -> H100 only (native FP8; near-lossless)
#   Qwen/Qwen3.6-27B-AWQ-INT4   ~15GB       -> any GPU incl. A100 40GB (frugal)
# Needs vllm>=0.19.0.
export BPX_TEACHER_HF="${BPX_TEACHER_HF:-Qwen/Qwen3.6-27B}"
export BPX_TEACHER_DIR="$BPX_PROJECT_DIR/models/teacher"          # pre-staged teacher weights
export BPX_DATASETS_DIR="$BPX_PROJECT_DIR/datasets"               # staged open instruction sets (offline)
export BPX_BANK="$BPX_WORK_DIR/bank.jsonl"                        # built prompt bank (build_bank.py)
# bf16 27B is ~54GB -> needs an 80GB A100 (there are some in gpu-batch). AND-constraint syntax.
# For a 40GB A100, switch BPX_TEACHER_HF to Qwen/Qwen3.6-27B-AWQ-INT4 and drop the GPU_MEM part.
export BPX_TEACHER_CONSTRAINT="${BPX_TEACHER_CONSTRAINT:-GPU_SKU:A100&GPU_MEM:80GB}"

# vLLM runs in its OWN container (its torch pins conflict with the NGC training image), imported
# once to a squashfs like the training image. Needs a vLLM >=0.19 for Qwen3.6 (check the tag).
export BPX_VLLM_IMAGE_URI="${BPX_VLLM_IMAGE_URI:-docker.io#vllm/vllm-openai:latest}"
export BPX_VLLM_SQSH="${BPX_VLLM_SQSH:-$BPX_PROJECT_DIR/images/vllm.sqsh}"
